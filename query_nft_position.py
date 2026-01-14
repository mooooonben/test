#!/usr/bin/env python3
"""
查询 Jupiter Multiply NFT 仓位凭证
"""

import asyncio
import aiohttp
import json
import base64

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
RPC_URL = "https://api.mainnet-beta.solana.com"

# Metaplex Token Metadata Program
METAPLEX_PROGRAM = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    """调用 RPC"""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
        return await response.json()


async def get_token_accounts(session: aiohttp.ClientSession, address: str) -> list:
    """获取所有代币账户"""
    result = await rpc_call(session, "getTokenAccountsByOwner", [
        address,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"}
    ])
    return result.get("result", {}).get("value", [])


async def get_nft_metadata(session: aiohttp.ClientSession, mint: str) -> dict:
    """获取 NFT 元数据"""
    from base58 import b58decode, b58encode
    import hashlib
    
    # 计算 Metadata PDA
    # seeds: ["metadata", program_id, mint]
    program_id = b58decode(METAPLEX_PROGRAM)
    mint_bytes = b58decode(mint)
    
    # 找到 PDA
    seeds = [b"metadata", program_id, mint_bytes]
    
    # 简化：直接查询已知的 metadata 账户模式
    # 使用 getProgramAccounts 查找
    result = await rpc_call(session, "getProgramAccounts", [
        METAPLEX_PROGRAM,
        {
            "encoding": "jsonParsed",
            "filters": [
                {"memcmp": {"offset": 33, "bytes": mint}}  # mint 在 metadata 账户的 offset 33
            ]
        }
    ])
    
    accounts = result.get("result", [])
    if accounts:
        return accounts[0]
    return {}


async def get_account_info(session: aiohttp.ClientSession, address: str, encoding: str = "jsonParsed") -> dict:
    """获取账户信息"""
    result = await rpc_call(session, "getAccountInfo", [address, {"encoding": encoding}])
    return result.get("result", {})


async def parse_metadata(data_bytes: bytes) -> dict:
    """解析 Metaplex metadata"""
    try:
        # Metaplex Metadata 结构
        # key (1) + update_authority (32) + mint (32) + name (variable) + symbol (variable) + uri (variable)
        
        offset = 1  # skip key
        
        # update_authority (32 bytes)
        update_authority = base64.b64encode(data_bytes[offset:offset+32]).decode()
        offset += 32
        
        # mint (32 bytes)
        from base58 import b58encode
        mint = b58encode(data_bytes[offset:offset+32]).decode()
        offset += 32
        
        # name (4 bytes length + string)
        name_len = int.from_bytes(data_bytes[offset:offset+4], 'little')
        offset += 4
        name = data_bytes[offset:offset+name_len].decode('utf-8').rstrip('\x00')
        offset += name_len
        
        # symbol (4 bytes length + string)
        symbol_len = int.from_bytes(data_bytes[offset:offset+4], 'little')
        offset += 4
        symbol = data_bytes[offset:offset+symbol_len].decode('utf-8').rstrip('\x00')
        offset += symbol_len
        
        # uri (4 bytes length + string)
        uri_len = int.from_bytes(data_bytes[offset:offset+4], 'little')
        offset += 4
        uri = data_bytes[offset:offset+uri_len].decode('utf-8').rstrip('\x00')
        
        return {
            "mint": mint,
            "name": name,
            "symbol": symbol,
            "uri": uri
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_uri_metadata(session: aiohttp.ClientSession, uri: str) -> dict:
    """获取 URI 指向的元数据"""
    try:
        # 处理 IPFS 链接
        if uri.startswith("ipfs://"):
            uri = uri.replace("ipfs://", "https://ipfs.io/ipfs/")
        
        async with session.get(uri, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        return {"error": str(e)}
    return {}


async def main():
    print("=" * 80)
    print(f"🔍 查询 Jupiter Multiply NFT 仓位凭证")
    print(f"   地址: {TARGET_ADDRESS}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 获取所有代币账户，找出 NFT (余额=1, decimals=0)
        print("\n📊 1. 查找 NFT 代币账户")
        
        token_accounts = await get_token_accounts(session, TARGET_ADDRESS)
        
        nfts = []
        for acc in token_accounts:
            try:
                parsed = acc["account"]["data"]["parsed"]["info"]
                mint = parsed["mint"]
                balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
                decimals = parsed["tokenAmount"]["decimals"]
                
                # NFT: 余额为1，decimals为0
                if balance == 1.0 and decimals == 0:
                    nfts.append({
                        "mint": mint,
                        "account": acc["pubkey"]
                    })
                    print(f"\n   ✅ 找到 NFT:")
                    print(f"      Mint: {mint}")
                    print(f"      Token Account: {acc['pubkey']}")
            except Exception as e:
                pass
        
        if not nfts:
            print("   ❌ 未找到 NFT")
            return
        
        # 2. 获取每个 NFT 的元数据
        print("\n" + "=" * 40)
        print("📊 2. 获取 NFT 元数据")
        print("=" * 40)
        
        for nft in nfts:
            mint = nft["mint"]
            print(f"\n   查询 Mint: {mint}")
            
            # 查询 Metaplex metadata 账户
            metadata_accounts = await rpc_call(session, "getProgramAccounts", [
                METAPLEX_PROGRAM,
                {
                    "encoding": "base64",
                    "filters": [
                        {"memcmp": {"offset": 33, "bytes": mint}}
                    ]
                }
            ])
            
            accounts = metadata_accounts.get("result", [])
            if accounts:
                print(f"   找到 Metadata 账户: {accounts[0]['pubkey']}")
                
                # 解析 metadata
                data_b64 = accounts[0]["account"]["data"][0]
                data_bytes = base64.b64decode(data_b64)
                
                metadata = await parse_metadata(data_bytes)
                print(f"\n   📋 NFT 元数据:")
                print(f"      名称: {metadata.get('name', 'N/A')}")
                print(f"      符号: {metadata.get('symbol', 'N/A')}")
                print(f"      URI: {metadata.get('uri', 'N/A')}")
                
                # 获取 URI 指向的 JSON 元数据
                uri = metadata.get('uri', '')
                if uri:
                    print(f"\n   📥 获取 URI 元数据...")
                    uri_metadata = await fetch_uri_metadata(session, uri)
                    if uri_metadata and "error" not in uri_metadata:
                        print(f"\n   📋 URI 元数据内容:")
                        print(json.dumps(uri_metadata, indent=2, ensure_ascii=False))
                        
                        # 查找仓位相关属性
                        attributes = uri_metadata.get("attributes", [])
                        if attributes:
                            print(f"\n   📊 仓位属性:")
                            for attr in attributes:
                                trait = attr.get("trait_type", "")
                                value = attr.get("value", "")
                                print(f"      {trait}: {value}")
                    else:
                        print(f"   ⚠️ 无法获取 URI 元数据: {uri_metadata}")
            else:
                print(f"   ⚠️ 未找到 Metadata 账户")
        
        # 3. 尝试直接解析 NFT 关联的仓位数据
        print("\n" + "=" * 40)
        print("📊 3. 查找 NFT 关联的仓位账户")
        print("=" * 40)
        
        for nft in nfts:
            mint = nft["mint"]
            
            # Jupiter Multiply 可能有专门的 Program 存储仓位数据
            # 尝试用 mint 作为过滤条件查找相关账户
            
            # 已知可能的 Jupiter Multiply Program IDs
            multiply_programs = [
                "6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc",  # 可能的 Multiply Program
                "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M",  # Kamino Lending
            ]
            
            for program in multiply_programs:
                print(f"\n   查询 Program: {program[:20]}...")
                
                # 用 NFT mint 作为过滤条件
                result = await rpc_call(session, "getProgramAccounts", [
                    program,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"memcmp": {"offset": 0, "bytes": mint}}
                        ]
                    }
                ])
                
                accounts = result.get("result", [])
                if accounts:
                    print(f"   ✅ 找到 {len(accounts)} 个关联账户!")
                    for acc in accounts:
                        print(f"      - {acc['pubkey']}")
                
                await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
