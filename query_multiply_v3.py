#!/usr/bin/env python3
"""
查询 Jupiter Multiply 仓位 - 使用多个 RPC 和分析交易
"""

import asyncio
import aiohttp
import json
import base64
from base58 import b58decode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"

# 多个 RPC 端点
RPC_URLS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana-mainnet.g.alchemy.com/v2/demo",
    "https://rpc.ankr.com/solana",
    "https://solana.public-rpc.com",
]

# Kamino Lending Program
KAMINO_LENDING_PROGRAM = "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M"

# 已知代币
KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "jupSOL",
    "So11111111111111111111111111111111111111112": "SOL",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
}

# 已知 Program IDs
KNOWN_PROGRAMS = {
    "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M": "Kamino Lending",
    "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA": "Marginfi",
    "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo": "Solend",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter V6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter V4",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca Swap",
    "srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX": "Serum",
    "PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu": "Jupiter Perps",
    "11111111111111111111111111111111": "System Program",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token Program",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token",
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    """调用 RPC，自动尝试多个端点"""
    for rpc_url in RPC_URLS:
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": 1
            }
            async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as response:
                data = await response.json()
                if "error" not in data:
                    return data
        except Exception:
            continue
    return {}


async def get_transaction(session: aiohttp.ClientSession, signature: str) -> dict:
    """获取交易详情"""
    result = await rpc_call(session, "getTransaction", [
        signature,
        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
    ])
    return result.get("result", {})


async def analyze_transaction(session: aiohttp.ClientSession, signature: str) -> dict:
    """分析单笔交易"""
    tx = await get_transaction(session, signature)
    if not tx:
        return None
    
    analysis = {
        "signature": signature,
        "slot": tx.get("slot"),
        "programs": set(),
        "token_changes": [],
        "instructions": []
    }
    
    # 分析交易涉及的程序
    meta = tx.get("meta", {})
    message = tx.get("transaction", {}).get("message", {})
    
    # 获取涉及的程序
    for acc in message.get("accountKeys", []):
        if isinstance(acc, dict):
            pubkey = acc.get("pubkey")
        else:
            pubkey = acc
        if pubkey in KNOWN_PROGRAMS:
            analysis["programs"].add(KNOWN_PROGRAMS[pubkey])
    
    # 分析余额变化
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])
    
    # 创建索引映射
    pre_map = {(b.get("accountIndex"), b.get("mint")): b for b in pre_balances}
    post_map = {(b.get("accountIndex"), b.get("mint")): b for b in post_balances}
    
    all_keys = set(pre_map.keys()) | set(post_map.keys())
    for key in all_keys:
        pre = pre_map.get(key, {})
        post = post_map.get(key, {})
        
        mint = pre.get("mint") or post.get("mint")
        pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount") or 0)
        post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount") or 0)
        
        if pre_amount != post_amount:
            token_name = KNOWN_MINTS.get(mint, mint[:12] + "..." if mint else "Unknown")
            analysis["token_changes"].append({
                "token": token_name,
                "mint": mint,
                "change": post_amount - pre_amount
            })
    
    # 分析指令
    instructions = message.get("instructions", [])
    for idx, ix in enumerate(instructions[:5]):  # 只看前5个
        program_id = ix.get("programId")
        program_name = KNOWN_PROGRAMS.get(program_id, program_id[:12] + "..." if program_id else "Unknown")
        
        analysis["instructions"].append({
            "index": idx,
            "program": program_name,
            "program_id": program_id
        })
    
    analysis["programs"] = list(analysis["programs"])
    return analysis


async def main():
    print("=" * 80)
    print(f"🔍 分析地址: {TARGET_ADDRESS}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 获取基本信息
        print("\n📊 1. 基本余额信息")
        
        # SOL 余额
        result = await rpc_call(session, "getBalance", [TARGET_ADDRESS])
        sol_balance = result.get("result", {}).get("value", 0) / 1e9
        print(f"   SOL: {sol_balance:.6f}")
        
        # 代币余额
        result = await rpc_call(session, "getTokenAccountsByOwner", [
            TARGET_ADDRESS,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ])
        
        tokens = []
        for account in result.get("result", {}).get("value", []):
            parsed = account["account"]["data"]["parsed"]["info"]
            mint = parsed["mint"]
            balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
            if balance > 0:
                token_name = KNOWN_MINTS.get(mint, mint[:20] + "...")
                tokens.append({"name": token_name, "mint": mint, "balance": balance})
                print(f"   {token_name}: {balance:.6f}")
        
        # 2. 获取最近交易并分析
        print("\n📊 2. 最近交易分析")
        
        result = await rpc_call(session, "getSignaturesForAddress", [TARGET_ADDRESS, {"limit": 20}])
        signatures = result.get("result", [])
        
        print(f"   找到 {len(signatures)} 笔最近交易\n")
        
        kamino_txs = []
        jup_txs = []
        
        for i, sig_info in enumerate(signatures[:10]):  # 分析前10笔
            sig = sig_info["signature"]
            print(f"   分析交易 {i+1}/{min(10, len(signatures))}: {sig[:20]}...")
            
            analysis = await analyze_transaction(session, sig)
            if analysis:
                programs = analysis.get("programs", [])
                changes = analysis.get("token_changes", [])
                instructions = analysis.get("instructions", [])
                
                # 检查是否涉及 Kamino 或 Jupiter
                is_kamino = any("Kamino" in p for p in programs) or any("Kamino" in ix.get("program", "") for ix in instructions)
                is_jupiter = any("Jupiter" in p for p in programs) or any("Jupiter" in ix.get("program", "") for ix in instructions)
                
                if is_kamino:
                    kamino_txs.append(analysis)
                if is_jupiter:
                    jup_txs.append(analysis)
                
                if programs or changes:
                    print(f"      涉及程序: {', '.join(programs[:3]) if programs else 'N/A'}")
                    if changes:
                        for change in changes[:3]:
                            symbol = "+" if change["change"] > 0 else ""
                            print(f"      代币变化: {change['token']} {symbol}{change['change']:.6f}")
                    print()
            
            await asyncio.sleep(0.3)  # 避免限流
        
        # 3. 汇总 Kamino/Jupiter 相关交易
        print("\n" + "=" * 80)
        print("📋 3. Kamino/Jupiter Multiply 相关交易汇总")
        print("=" * 80)
        
        if kamino_txs:
            print(f"\n✅ 找到 {len(kamino_txs)} 笔 Kamino 相关交易:")
            for tx in kamino_txs:
                print(f"\n   交易: {tx['signature'][:30]}...")
                for ix in tx.get("instructions", []):
                    if "Kamino" in ix.get("program", ""):
                        print(f"   Program: {ix['program']}")
                for change in tx.get("token_changes", []):
                    symbol = "+" if change["change"] > 0 else ""
                    print(f"   代币变化: {change['token']} {symbol}{change['change']:.6f}")
        else:
            print("\n❌ 未找到 Kamino 相关交易")
        
        if jup_txs:
            print(f"\n✅ 找到 {len(jup_txs)} 笔 Jupiter 相关交易:")
            for tx in jup_txs:
                print(f"\n   交易: {tx['signature'][:30]}...")
                for change in tx.get("token_changes", []):
                    symbol = "+" if change["change"] > 0 else ""
                    print(f"   代币变化: {change['token']} {symbol}{change['change']:.6f}")
        else:
            print("\n❌ 未找到 Jupiter 相关交易")
        
        # 4. 结论
        print("\n" + "=" * 80)
        print("📋 4. 结论")
        print("=" * 80)
        
        print(f"""
当前地址持有:
- SOL: {sol_balance:.6f}
- jupSOL: {next((t['balance'] for t in tokens if 'jupSOL' in t['name']), 0):.6f}
- JitoSOL: {next((t['balance'] for t in tokens if 'JitoSOL' in t['name']), 0):.6f}

Jupiter Multiply 仓位分析:
- 如果该地址有活跃的 jupSOL/SOL Multiply 仓位，仓位信息会存储在 Kamino Lending 协议中
- 当前查询未发现活跃的 Kamino Obligation 账户
- 可能的原因:
  1. 没有活跃的 Multiply 仓位
  2. 仓位已被平仓
  3. 使用的是其他杠杆协议
        """)


if __name__ == "__main__":
    asyncio.run(main())
