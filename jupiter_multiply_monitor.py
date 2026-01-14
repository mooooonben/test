#!/usr/bin/env python3
"""
Jupiter Multiply 仓位监控工具

Jupiter Multiply (jupSOL/SOL) 仓位信息获取方式：
1. 通过 NFT 凭证查找仓位
2. NFT 存储在 Jupiter Router Program 的账户中
3. 仓位数据分布在多个账户中

关键 Program IDs:
- Jupiter Vault: jupgfSgfuAXv4B6R2Uxu85Z1qdzgju79s6MfZekN6XS
- Jupiter Router: jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi
- Jupiter Stake Pool: jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC
"""

import asyncio
import aiohttp
import json
import base64
import struct
from base58 import b58decode, b58encode
from typing import Optional, Dict, List

RPC_URL = "https://api.mainnet-beta.solana.com"

# Jupiter 相关 Program IDs
JUPITER_VAULT_PROGRAM = "jupgfSgfuAXv4B6R2Uxu85Z1qdzgju79s6MfZekN6XS"
JUPITER_ROUTER_PROGRAM = "jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi"
JUPITER_STAKE_POOL_PROGRAM = "jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC"
METAPLEX_PROGRAM = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"

# 已知 mints
KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": ("jupSOL", 9),
    "So11111111111111111111111111111111111111112": ("wSOL", 9),
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    """调用 Solana RPC"""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def get_token_accounts(session: aiohttp.ClientSession, owner: str) -> List[dict]:
    """获取用户的所有代币账户"""
    result = await rpc_call(session, "getTokenAccountsByOwner", [
        owner,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"}
    ])
    return result.get("result", {}).get("value", [])


async def find_multiply_nfts(session: aiohttp.ClientSession, owner: str) -> List[dict]:
    """查找用户持有的 Jupiter Multiply NFT"""
    nfts = []
    token_accounts = await get_token_accounts(session, owner)
    
    for acc in token_accounts:
        try:
            parsed = acc["account"]["data"]["parsed"]["info"]
            mint = parsed["mint"]
            balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
            decimals = parsed["tokenAmount"]["decimals"]
            
            # NFT: balance=1, decimals=0
            if balance == 1.0 and decimals == 0:
                # 检查是否是 Jupiter Multiply NFT
                metadata = await get_nft_metadata(session, mint)
                if metadata and "jupiter" in metadata.get("name", "").lower():
                    nfts.append({
                        "mint": mint,
                        "token_account": acc["pubkey"],
                        "metadata": metadata
                    })
        except:
            continue
    
    return nfts


async def get_nft_metadata(session: aiohttp.ClientSession, mint: str) -> Optional[dict]:
    """获取 NFT 元数据"""
    result = await rpc_call(session, "getProgramAccounts", [
        METAPLEX_PROGRAM,
        {
            "encoding": "base64",
            "filters": [
                {"memcmp": {"offset": 33, "bytes": mint}}
            ]
        }
    ])
    
    accounts = result.get("result", [])
    if not accounts:
        return None
    
    try:
        data = base64.b64decode(accounts[0]["account"]["data"][0])
        return parse_metadata(data)
    except:
        return None


def parse_metadata(data: bytes) -> dict:
    """解析 Metaplex 元数据"""
    try:
        offset = 1 + 32  # skip key and update_authority
        
        # mint (32 bytes)
        mint = b58encode(data[offset:offset+32]).decode()
        offset += 32
        
        # name
        name_len = int.from_bytes(data[offset:offset+4], 'little')
        offset += 4
        name = data[offset:offset+name_len].decode('utf-8').rstrip('\x00')
        offset += name_len
        
        # symbol
        symbol_len = int.from_bytes(data[offset:offset+4], 'little')
        offset += 4
        symbol = data[offset:offset+symbol_len].decode('utf-8').rstrip('\x00')
        offset += symbol_len
        
        # uri
        uri_len = int.from_bytes(data[offset:offset+4], 'little')
        offset += 4
        uri = data[offset:offset+uri_len].decode('utf-8').rstrip('\x00')
        
        return {"mint": mint, "name": name, "symbol": symbol, "uri": uri}
    except:
        return {}


async def find_position_account(session: aiohttp.ClientSession, nft_mint: str) -> Optional[str]:
    """通过 NFT mint 查找仓位账户"""
    # 在 Jupiter Router Program 中查找包含 NFT mint 的账户
    result = await rpc_call(session, "getProgramAccounts", [
        JUPITER_ROUTER_PROGRAM,
        {
            "encoding": "base64",
            "filters": [
                {"memcmp": {"offset": 14, "bytes": nft_mint}}  # NFT mint at offset 14
            ]
        }
    ])
    
    accounts = result.get("result", [])
    if accounts:
        return accounts[0]["pubkey"]
    return None


async def get_position_details(session: aiohttp.ClientSession, owner: str, nft_mint: str) -> dict:
    """获取仓位详细信息"""
    position = {
        "owner": owner,
        "nft_mint": nft_mint,
        "accounts": []
    }
    
    # 获取 NFT token account 的交易历史来找到相关账户
    # 获取 NFT token account
    result = await rpc_call(session, "getTokenAccountsByOwner", [
        owner,
        {"mint": nft_mint},
        {"encoding": "jsonParsed"}
    ])
    
    nft_accounts = result.get("result", {}).get("value", [])
    if not nft_accounts:
        return position
    
    nft_token_account = nft_accounts[0]["pubkey"]
    position["nft_token_account"] = nft_token_account
    
    # 获取最近的交易
    result = await rpc_call(session, "getSignaturesForAddress", [
        nft_token_account,
        {"limit": 3}
    ])
    
    signatures = result.get("result", [])
    if not signatures:
        return position
    
    # 分析最近的交易找到仓位相关账户
    sig = signatures[0]["signature"]
    tx_result = await rpc_call(session, "getTransaction", [
        sig,
        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
    ])
    
    tx = tx_result.get("result")
    if not tx:
        return position
    
    # 提取涉及的账户
    message = tx.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys", [])
    
    for acc in account_keys:
        pubkey = acc.get("pubkey") if isinstance(acc, dict) else acc
        
        # 获取账户信息
        acc_result = await rpc_call(session, "getAccountInfo", [pubkey, {"encoding": "base64"}])
        acc_info = acc_result.get("result", {}).get("value")
        
        if acc_info:
            owner_program = acc_info.get("owner")
            
            # 只关注 Jupiter 相关程序的账户
            if owner_program in [JUPITER_VAULT_PROGRAM, JUPITER_ROUTER_PROGRAM, JUPITER_STAKE_POOL_PROGRAM]:
                data = acc_info.get("data", [])
                if data and data[0]:
                    data_bytes = base64.b64decode(data[0])
                    
                    account_info = {
                        "pubkey": pubkey,
                        "owner": owner_program,
                        "data_length": len(data_bytes),
                    }
                    
                    # 检查包含的代币
                    for mint_str, (name, decimals) in KNOWN_MINTS.items():
                        mint_bytes = b58decode(mint_str)
                        if mint_bytes in data_bytes:
                            account_info[f"contains_{name}"] = True
                    
                    # 检查是否包含 NFT mint
                    try:
                        nft_bytes = b58decode(nft_mint)
                        if nft_bytes in data_bytes:
                            account_info["contains_nft"] = True
                    except:
                        pass
                    
                    position["accounts"].append(account_info)
    
    return position


async def query_multiply_position(owner: str) -> dict:
    """查询用户的 Jupiter Multiply 仓位"""
    print(f"\n🔍 查询 Jupiter Multiply 仓位")
    print(f"   地址: {owner}")
    print("=" * 60)
    
    result = {
        "owner": owner,
        "positions": []
    }
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 获取基本余额
        print("\n📊 基本余额:")
        
        # SOL
        sol_result = await rpc_call(session, "getBalance", [owner])
        sol_balance = sol_result.get("result", {}).get("value", 0) / 1e9
        result["sol_balance"] = sol_balance
        print(f"   SOL: {sol_balance:.6f}")
        
        # 代币
        token_accounts = await get_token_accounts(session, owner)
        result["tokens"] = []
        
        for acc in token_accounts:
            try:
                parsed = acc["account"]["data"]["parsed"]["info"]
                mint = parsed["mint"]
                balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
                
                if balance > 0:
                    mint_name = KNOWN_MINTS.get(mint, (mint[:12] + "...", 9))[0]
                    result["tokens"].append({"mint": mint, "name": mint_name, "balance": balance})
                    
                    if mint in KNOWN_MINTS:
                        print(f"   {mint_name}: {balance:.6f}")
            except:
                continue
        
        # 2. 查找 Multiply NFT
        print("\n📊 查找 Jupiter Multiply NFT:")
        
        nfts = await find_multiply_nfts(session, owner)
        
        if nfts:
            for nft in nfts:
                print(f"\n   ✅ 找到 NFT: {nft['metadata'].get('name', 'Unknown')}")
                print(f"      Mint: {nft['mint']}")
                print(f"      Symbol: {nft['metadata'].get('symbol', '')}")
                print(f"      URI: {nft['metadata'].get('uri', '')}")
                
                # 获取仓位详情
                print(f"\n   📋 仓位详情:")
                position = await get_position_details(session, owner, nft["mint"])
                
                print(f"      NFT Token Account: {position.get('nft_token_account', 'N/A')}")
                print(f"      关联账户数: {len(position.get('accounts', []))}")
                
                for acc in position.get("accounts", []):
                    print(f"\n      账户: {acc['pubkey'][:30]}...")
                    print(f"         Owner: {acc['owner'][:30]}...")
                    print(f"         Data: {acc['data_length']} bytes")
                    if acc.get("contains_jupSOL"):
                        print(f"         包含: jupSOL ✅")
                    if acc.get("contains_wSOL"):
                        print(f"         包含: wSOL ✅")
                    if acc.get("contains_nft"):
                        print(f"         包含: NFT ✅")
                
                result["positions"].append({
                    "nft": nft,
                    "details": position
                })
        else:
            print("   ❌ 未找到 Jupiter Multiply NFT")
    
    return result


async def main():
    import sys
    
    if len(sys.argv) > 1:
        owner = sys.argv[1]
    else:
        owner = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
    
    result = await query_multiply_position(owner)
    
    print("\n" + "=" * 60)
    print("📋 总结")
    print("=" * 60)
    
    print(f"""
Jupiter Multiply 仓位信息来源：

1. **NFT 凭证**
   - 每个 Multiply 仓位都有一个对应的 NFT
   - NFT 元数据包含仓位类型信息 (如 jupSOL/SOL)
   - 元数据 URI 来自 Instadapp CDN

2. **仓位数据存储**
   - 仓位账户由 Jupiter Router Program 管理
   - Program: jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi
   - 通过 NFT mint 在 offset 14 位置可以找到仓位账户

3. **相关 Programs**
   - Jupiter Vault: jupgfSgfuAXv4B6R2Uxu85Z1qdzgju79s6MfZekN6XS
   - Jupiter Router: jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi
   - Jupiter Stake Pool: jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC

4. **查询方法**
   a. 获取用户的 NFT (decimals=0, balance=1)
   b. 检查 NFT 元数据是否包含 "jupiter"
   c. 通过 NFT token account 的交易历史找到仓位相关账户
   d. 解析账户数据获取仓位详情
    """)
    
    if result["positions"]:
        print(f"\n当前仓位数量: {len(result['positions'])}")
        for i, pos in enumerate(result["positions"], 1):
            print(f"\n仓位 #{i}:")
            print(f"  名称: {pos['nft']['metadata'].get('name', 'Unknown')}")
            print(f"  NFT Mint: {pos['nft']['mint']}")


if __name__ == "__main__":
    asyncio.run(main())
