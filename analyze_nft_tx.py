#!/usr/bin/env python3
"""
分析 NFT 仓位相关的交易，找出仓位数据存储位置
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

# NFT 相关的交易签名
TX_SIGNATURES = [
    "5mwm7CxbeLuZggF3i25PeBqq8Gc2UiuuNF2ZwzhTPTYYUDzFcBxH8zJPEbvxbkZDJaVPyhcxPEdFPJq1r2S8rNJL",
    "3RhfgaDKtLHoPNnhqzyhDBJnZoYbYuQwydWrDanLjBNTAq6DYDvLc1Gbi8oSvTjZoJqGbhzMNaKqhXVQ8Fw8dcff",
    "2ojZXHuxBNZsCp4ioqWB7UjRNTPbhLntGpLAcVZmJShEz8aCJDbkfJ6YCZKdjnM1XAMxQVSP7uYEDqNVvVNp7CnX",
]

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
    "ComputeBudget111111111111111111111111111111": "Compute Budget",
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s": "Metaplex Metadata",
}

KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "jupSOL",
    "So11111111111111111111111111111111111111112": "wSOL",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    """调用 RPC"""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def get_transaction(session: aiohttp.ClientSession, signature: str) -> dict:
    """获取交易详情"""
    result = await rpc_call(session, "getTransaction", [
        signature,
        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
    ])
    return result.get("result", {})


async def analyze_transaction(tx: dict) -> dict:
    """分析交易"""
    if not tx:
        return {}
    
    analysis = {
        "slot": tx.get("slot"),
        "programs": [],
        "accounts": [],
        "instructions": [],
        "token_changes": [],
    }
    
    message = tx.get("transaction", {}).get("message", {})
    meta = tx.get("meta", {})
    
    # 获取所有账户
    account_keys = message.get("accountKeys", [])
    for i, acc in enumerate(account_keys):
        if isinstance(acc, dict):
            pubkey = acc.get("pubkey")
            is_signer = acc.get("signer", False)
            is_writable = acc.get("writable", False)
        else:
            pubkey = acc
            is_signer = False
            is_writable = False
        
        analysis["accounts"].append({
            "index": i,
            "pubkey": pubkey,
            "name": KNOWN_PROGRAMS.get(pubkey, ""),
            "signer": is_signer,
            "writable": is_writable
        })
        
        if pubkey in KNOWN_PROGRAMS:
            analysis["programs"].append(KNOWN_PROGRAMS[pubkey])
    
    # 分析指令
    instructions = message.get("instructions", [])
    for i, ix in enumerate(instructions):
        program_id = ix.get("programId")
        program_name = KNOWN_PROGRAMS.get(program_id, program_id[:20] + "..." if program_id else "")
        
        ix_info = {
            "index": i,
            "program": program_name,
            "program_id": program_id,
        }
        
        # 如果是已解析的指令
        if "parsed" in ix:
            ix_info["parsed"] = ix["parsed"]
        
        # 涉及的账户
        if "accounts" in ix:
            ix_info["accounts"] = ix["accounts"][:10]  # 只显示前10个
        
        analysis["instructions"].append(ix_info)
    
    # 分析内部指令
    inner_instructions = meta.get("innerInstructions", [])
    for inner in inner_instructions:
        for ix in inner.get("instructions", []):
            program_id = ix.get("programId")
            if program_id and program_id not in [p for p in analysis["programs"]]:
                program_name = KNOWN_PROGRAMS.get(program_id, program_id[:20] + "...")
                analysis["programs"].append(program_name)
    
    # 分析代币变化
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])
    
    pre_map = {(b.get("accountIndex"), b.get("mint")): b for b in pre_balances}
    post_map = {(b.get("accountIndex"), b.get("mint")): b for b in post_balances}
    
    for key in set(pre_map.keys()) | set(post_map.keys()):
        pre = pre_map.get(key, {})
        post = post_map.get(key, {})
        
        mint = pre.get("mint") or post.get("mint")
        owner = pre.get("owner") or post.get("owner")
        pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount") or 0)
        post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount") or 0)
        
        change = post_amount - pre_amount
        if abs(change) > 0.000001:
            token_name = KNOWN_MINTS.get(mint, mint[:16] + "..." if mint else "")
            analysis["token_changes"].append({
                "token": token_name,
                "mint": mint,
                "owner": owner,
                "change": change
            })
    
    return analysis


async def get_account_info(session: aiohttp.ClientSession, address: str) -> dict:
    """获取账户信息"""
    result = await rpc_call(session, "getAccountInfo", [address, {"encoding": "base64"}])
    return result.get("result", {})


async def main():
    print("=" * 80)
    print(f"🔍 分析 NFT 仓位相关交易")
    print(f"   NFT Mint: {NFT_MINT}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 分析每笔交易
        all_accounts = set()
        all_programs = set()
        
        for sig in TX_SIGNATURES:
            print(f"\n{'='*60}")
            print(f"📋 交易: {sig[:40]}...")
            print("=" * 60)
            
            tx = await get_transaction(session, sig)
            if not tx:
                print("   ❌ 无法获取交易")
                continue
            
            analysis = await analyze_transaction(tx)
            
            # 显示涉及的程序
            print(f"\n   涉及的程序:")
            for prog in analysis.get("programs", []):
                print(f"   - {prog}")
                all_programs.add(prog)
            
            # 显示代币变化
            print(f"\n   代币变化:")
            for change in analysis.get("token_changes", []):
                symbol = "+" if change["change"] > 0 else ""
                print(f"   - {change['token']}: {symbol}{change['change']:.6f}")
                print(f"     Owner: {change['owner'][:20]}..." if change['owner'] else "")
            
            # 显示关键账户 (writable 账户可能是仓位账户)
            print(f"\n   可写账户 (可能包含仓位数据):")
            for acc in analysis.get("accounts", []):
                if acc["writable"] and not acc["signer"]:
                    pubkey = acc["pubkey"]
                    name = acc["name"] or pubkey[:20] + "..."
                    print(f"   - [{acc['index']}] {name}")
                    print(f"     {pubkey}")
                    all_accounts.add(pubkey)
            
            # 显示指令详情
            print(f"\n   指令:")
            for ix in analysis.get("instructions", [])[:5]:
                print(f"   [{ix['index']}] {ix['program']}")
                if ix.get("parsed"):
                    print(f"       Type: {ix['parsed'].get('type', 'N/A')}")
            
            await asyncio.sleep(1)
        
        # 汇总
        print("\n" + "=" * 80)
        print("📋 汇总: 发现的关键账户")
        print("=" * 80)
        
        # 过滤掉已知的程序账户
        unknown_accounts = []
        for acc in all_accounts:
            if acc not in KNOWN_PROGRAMS and acc != TARGET_ADDRESS:
                unknown_accounts.append(acc)
        
        print(f"\n   发现 {len(unknown_accounts)} 个可能的仓位相关账户:")
        
        for acc in unknown_accounts[:20]:
            print(f"\n   📋 账户: {acc}")
            
            # 获取账户信息
            info = await get_account_info(session, acc)
            if info.get("value"):
                owner = info["value"].get("owner")
                data = info["value"].get("data", [])
                data_len = len(base64.b64decode(data[0])) if data and data[0] else 0
                
                owner_name = KNOWN_PROGRAMS.get(owner, owner[:20] + "..." if owner else "")
                print(f"      Owner: {owner_name}")
                print(f"      Data Length: {data_len} bytes")
                
                # 如果是借贷相关 Program，尝试解析
                if owner in ["KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M",
                            "kvauTFR8qm1dhniz6pYuBZkuene3Hfrs1VQhVRgCNrr",
                            "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"]:
                    print("      ⚠️ 这可能是仓位账户!")
                    
                    # 解析数据
                    if data and data[0]:
                        data_bytes = base64.b64decode(data[0])
                        print(f"      前 64 字节: {data_bytes[:64].hex()}")
            
            await asyncio.sleep(0.3)
        
        print("\n" + "=" * 80)
        print("📋 使用的 DeFi 程序")
        print("=" * 80)
        for prog in all_programs:
            print(f"   - {prog}")


if __name__ == "__main__":
    asyncio.run(main())
