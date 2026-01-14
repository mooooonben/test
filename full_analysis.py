#!/usr/bin/env python3
"""
完整分析 Jupiter Multiply 仓位
"""

import asyncio
import aiohttp
import json
import base64
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"
NFT_TOKEN_ACCOUNT = "CVxBujMbbNszmGygDbi12Dy8NCAjw5dYNeX3z6NmhjKS"

RPC_URL = "https://api.mainnet-beta.solana.com"

KNOWN_PROGRAMS = {
    "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M": "Kamino Lending",
    "kvauTFR8qm1dhniz6pYuBZkuene3Hfrs1VQhVRgCNrr": "Kamino Vault",
    "6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc": "Kamino Farms",
    "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA": "Marginfi",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter V6",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token Program",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "AToken Program",
    "11111111111111111111111111111111": "System Program",
}

KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "jupSOL",
    "So11111111111111111111111111111111111111112": "wSOL",
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    """调用 RPC"""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def main():
    print("=" * 80)
    print(f"🔍 完整分析 Jupiter Multiply 仓位")
    print(f"   地址: {TARGET_ADDRESS}")
    print(f"   NFT: {NFT_MINT}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 先获取 NFT token account 的交易签名
        print("\n📊 1. 获取 NFT 相关交易")
        
        result = await rpc_call(session, "getSignaturesForAddress", [
            NFT_TOKEN_ACCOUNT,
            {"limit": 10}
        ])
        
        signatures = result.get("result", [])
        print(f"   找到 {len(signatures)} 笔交易")
        
        for sig_info in signatures:
            print(f"   - {sig_info['signature']}")
        
        if not signatures:
            print("   ❌ 未找到交易")
            return
        
        # 2. 分析第一笔交易 (最近的)
        print("\n📊 2. 分析最近的交易")
        
        sig = signatures[0]["signature"]
        print(f"   交易: {sig}")
        
        result = await rpc_call(session, "getTransaction", [
            sig,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        
        tx = result.get("result")
        if not tx:
            print(f"   ❌ 无法获取交易: {result.get('error', 'Unknown error')}")
        else:
            print("   ✅ 获取成功")
            
            # 提取关键账户
            message = tx.get("transaction", {}).get("message", {})
            meta = tx.get("meta", {})
            
            print("\n   涉及的账户:")
            account_keys = message.get("accountKeys", [])
            for i, acc in enumerate(account_keys[:20]):
                if isinstance(acc, dict):
                    pubkey = acc.get("pubkey")
                    writable = acc.get("writable", False)
                else:
                    pubkey = acc
                    writable = False
                
                name = KNOWN_PROGRAMS.get(pubkey, "")
                marker = "[W]" if writable else "   "
                print(f"   {marker} [{i:2d}] {pubkey[:30]}... {name}")
            
            # 提取指令涉及的程序
            print("\n   指令涉及的程序:")
            instructions = message.get("instructions", [])
            for ix in instructions:
                prog = ix.get("programId")
                name = KNOWN_PROGRAMS.get(prog, prog[:30] + "..." if prog else "")
                print(f"   - {name}")
            
            # 代币变化
            print("\n   代币变化:")
            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])
            
            for post in post_balances:
                mint = post.get("mint")
                owner = post.get("owner")
                amount = float(post.get("uiTokenAmount", {}).get("uiAmount") or 0)
                
                # 找到对应的 pre
                pre_amount = 0
                for pre in pre_balances:
                    if pre.get("accountIndex") == post.get("accountIndex"):
                        pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount") or 0)
                        break
                
                change = amount - pre_amount
                if abs(change) > 0.0001:
                    token_name = KNOWN_MINTS.get(mint, mint[:20] + "..." if mint else "")
                    symbol = "+" if change > 0 else ""
                    print(f"   {token_name}: {symbol}{change:.6f}")
                    print(f"      Owner: {owner[:30]}..." if owner else "")
        
        # 3. 检查 Kamino 相关账户
        print("\n" + "=" * 60)
        print("📊 3. 直接搜索 Kamino Lending 账户")
        print("=" * 60)
        
        # 使用 NFT mint 作为过滤条件
        # Kamino 的仓位账户可能在不同 offset 包含 NFT mint
        offsets = [0, 8, 16, 32, 40, 48, 64, 72, 80, 96, 104, 128, 136, 160, 168]
        
        kamino_program = "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M"
        
        for offset in offsets:
            print(f"   尝试 offset={offset}...", end=" ")
            
            result = await rpc_call(session, "getProgramAccounts", [
                kamino_program,
                {
                    "encoding": "base64",
                    "filters": [
                        {"memcmp": {"offset": offset, "bytes": NFT_MINT}}
                    ]
                }
            ])
            
            if "error" in result:
                print(f"Error: {result['error'].get('message', '')[:30]}")
            else:
                accounts = result.get("result", [])
                if accounts:
                    print(f"✅ 找到 {len(accounts)} 个!")
                    for acc in accounts:
                        print(f"      - {acc['pubkey']}")
                        
                        # 解析数据
                        if acc.get("account", {}).get("data"):
                            data = base64.b64decode(acc["account"]["data"][0])
                            print(f"        Data length: {len(data)} bytes")
                else:
                    print("无")
            
            await asyncio.sleep(0.5)
        
        # 4. 也尝试用用户地址搜索
        print("\n" + "=" * 60)
        print("📊 4. 用用户地址搜索 Kamino 账户")
        print("=" * 60)
        
        for offset in [8, 32, 40, 72, 104]:
            print(f"   尝试 offset={offset}...", end=" ")
            
            result = await rpc_call(session, "getProgramAccounts", [
                kamino_program,
                {
                    "encoding": "base64",
                    "filters": [
                        {"memcmp": {"offset": offset, "bytes": TARGET_ADDRESS}}
                    ]
                }
            ])
            
            if "error" in result:
                print(f"Error: {result['error'].get('message', '')[:30]}")
            else:
                accounts = result.get("result", [])
                if accounts:
                    print(f"✅ 找到 {len(accounts)} 个!")
                    for acc in accounts:
                        print(f"      - {acc['pubkey']}")
                else:
                    print("无")
            
            await asyncio.sleep(0.5)
        
        # 5. 检查 Marginfi (之前发现有账户)
        print("\n" + "=" * 60)
        print("📊 5. 查询 Marginfi 账户详情")
        print("=" * 60)
        
        marginfi_program = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"
        
        result = await rpc_call(session, "getProgramAccounts", [
            marginfi_program,
            {
                "encoding": "base64",
                "filters": [
                    {"memcmp": {"offset": 40, "bytes": TARGET_ADDRESS}}
                ]
            }
        ])
        
        accounts = result.get("result", [])
        if accounts:
            print(f"   ✅ 找到 {len(accounts)} 个 Marginfi 账户!")
            
            for acc in accounts:
                print(f"\n   📋 账户: {acc['pubkey']}")
                
                if acc.get("account", {}).get("data"):
                    data = base64.b64decode(acc["account"]["data"][0])
                    print(f"      Data length: {len(data)} bytes")
                    print(f"      Discriminator: {data[:8].hex()}")
                    
                    # 尝试找到 jupSOL 和 SOL mint
                    jupsol_mint = b58decode("jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v")
                    sol_mint = b58decode("So11111111111111111111111111111111111111112")
                    
                    if jupsol_mint in data:
                        pos = data.find(jupsol_mint)
                        print(f"      ✅ 找到 jupSOL mint at offset {pos}")
                    
                    if sol_mint in data:
                        pos = data.find(sol_mint)
                        print(f"      ✅ 找到 SOL mint at offset {pos}")
        else:
            print("   未找到 Marginfi 账户")


if __name__ == "__main__":
    asyncio.run(main())
