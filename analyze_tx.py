#!/usr/bin/env python3
"""
深入分析 Jupiter 相关交易
"""

import asyncio
import aiohttp
import json

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
JUPITER_TX = "5mwm7CxbeLuZggF3i25PeBqq8Gc2Ui6PjDLVjKJBYDbDVYCSMVE3sQDybdWkYBRb1MhT1LMTLiNxzLi5jLSqLR8T"

RPC_URL = "https://api.mainnet-beta.solana.com"

# 已知 Program IDs
KNOWN_PROGRAMS = {
    "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M": "Kamino Lending",
    "kvauTFR8qm1dhniz6pYuBZkuene3Hfrs1VQhVRgCNrr": "Kamino Vault",
    "6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc": "Kamino Multiply",
    "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA": "Marginfi",
    "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo": "Solend",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter V6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter V4",
    "JUP3c2Uh3WA4Ng34tw6kPd2G4C5BB21Xo36Je1s32Ph": "Jupiter V3",
    "PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu": "Jupiter Perps",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    "11111111111111111111111111111111": "System Program",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token Program",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token",
    "ComputeBudget111111111111111111111111111111": "Compute Budget",
}

KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "jupSOL",
    "So11111111111111111111111111111111111111112": "wSOL",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
}


async def get_transaction(session: aiohttp.ClientSession, signature: str) -> dict:
    """获取交易详情"""
    payload = {
        "jsonrpc": "2.0",
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        "id": 1
    }
    
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
        data = await response.json()
        return data.get("result", {})


async def get_signatures(session: aiohttp.ClientSession, address: str, limit: int = 50) -> list:
    """获取交易签名"""
    payload = {
        "jsonrpc": "2.0",
        "method": "getSignaturesForAddress",
        "params": [address, {"limit": limit}],
        "id": 1
    }
    
    async with session.post(RPC_URL, json=payload) as response:
        data = await response.json()
        return data.get("result", [])


def analyze_tx_programs(tx: dict) -> list:
    """分析交易涉及的所有程序"""
    programs = []
    
    message = tx.get("transaction", {}).get("message", {})
    
    # 从 accountKeys 获取程序
    for acc in message.get("accountKeys", []):
        if isinstance(acc, dict):
            pubkey = acc.get("pubkey")
            is_program = acc.get("signer") is False and acc.get("writable") is False
        else:
            pubkey = acc
            is_program = False
        
        if pubkey in KNOWN_PROGRAMS:
            programs.append({"id": pubkey, "name": KNOWN_PROGRAMS[pubkey]})
    
    # 从 instructions 获取程序
    for ix in message.get("instructions", []):
        program_id = ix.get("programId")
        if program_id and program_id not in [p["id"] for p in programs]:
            name = KNOWN_PROGRAMS.get(program_id, program_id)
            programs.append({"id": program_id, "name": name})
    
    # 从 innerInstructions 获取程序
    for inner in tx.get("meta", {}).get("innerInstructions", []):
        for ix in inner.get("instructions", []):
            program_id = ix.get("programId")
            if program_id and program_id not in [p["id"] for p in programs]:
                name = KNOWN_PROGRAMS.get(program_id, program_id)
                programs.append({"id": program_id, "name": name})
    
    return programs


def analyze_token_changes(tx: dict, target_address: str) -> list:
    """分析代币余额变化"""
    changes = []
    meta = tx.get("meta", {})
    
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])
    
    # 索引映射
    pre_map = {(b.get("accountIndex"), b.get("mint")): b for b in pre_balances}
    post_map = {(b.get("accountIndex"), b.get("mint")): b for b in post_balances}
    
    all_keys = set(pre_map.keys()) | set(post_map.keys())
    
    for key in all_keys:
        pre = pre_map.get(key, {})
        post = post_map.get(key, {})
        
        mint = pre.get("mint") or post.get("mint")
        owner = pre.get("owner") or post.get("owner")
        
        pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount") or 0)
        post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount") or 0)
        
        change = post_amount - pre_amount
        if abs(change) > 0.0000001:
            token_name = KNOWN_MINTS.get(mint, mint[:16] + "..." if mint else "Unknown")
            changes.append({
                "token": token_name,
                "mint": mint,
                "owner": owner,
                "change": change,
                "is_target": owner == target_address if owner else False
            })
    
    return changes


async def main():
    print("=" * 80)
    print(f"🔍 深入分析地址: {TARGET_ADDRESS}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 获取更多交易
        print("\n📊 获取最近 50 笔交易...")
        signatures = await get_signatures(session, TARGET_ADDRESS, 50)
        print(f"   找到 {len(signatures)} 笔交易")
        
        # 找出涉及 Kamino 或特殊程序的交易
        kamino_txs = []
        multiply_txs = []
        lending_txs = []
        
        print("\n📊 分析交易中涉及的程序...")
        
        for i, sig_info in enumerate(signatures):
            sig = sig_info["signature"]
            
            tx = await get_transaction(session, sig)
            if not tx:
                continue
            
            programs = analyze_tx_programs(tx)
            program_names = [p["name"] for p in programs]
            
            # 检查是否涉及借贷/杠杆相关程序
            is_kamino = any("Kamino" in name for name in program_names)
            is_marginfi = any("Marginfi" in name for name in program_names)
            is_solend = any("Solend" in name for name in program_names)
            is_perps = any("Perps" in name for name in program_names)
            
            if is_kamino or is_marginfi or is_solend or is_perps:
                changes = analyze_token_changes(tx, TARGET_ADDRESS)
                tx_info = {
                    "signature": sig,
                    "programs": program_names,
                    "changes": changes,
                    "slot": sig_info.get("slot")
                }
                
                if is_kamino:
                    kamino_txs.append(tx_info)
                if is_marginfi or is_solend:
                    lending_txs.append(tx_info)
                if is_perps:
                    multiply_txs.append(tx_info)
            
            # 打印进度
            if (i + 1) % 10 == 0:
                print(f"   已分析 {i + 1}/{len(signatures)} 笔交易...")
            
            await asyncio.sleep(0.2)  # 避免限流
        
        # 汇总结果
        print("\n" + "=" * 80)
        print("📋 借贷/杠杆相关交易汇总")
        print("=" * 80)
        
        if kamino_txs:
            print(f"\n✅ Kamino 相关交易 ({len(kamino_txs)} 笔):")
            for tx in kamino_txs[:5]:
                print(f"\n   交易: {tx['signature'][:40]}...")
                print(f"   涉及程序: {', '.join(tx['programs'][:5])}")
                for change in tx["changes"]:
                    if change.get("is_target"):
                        symbol = "+" if change["change"] > 0 else ""
                        print(f"   代币变化: {change['token']} {symbol}{change['change']:.6f}")
        
        if lending_txs:
            print(f"\n✅ 其他借贷协议交易 ({len(lending_txs)} 笔):")
            for tx in lending_txs[:5]:
                print(f"\n   交易: {tx['signature'][:40]}...")
                print(f"   涉及程序: {', '.join(tx['programs'][:5])}")
        
        if multiply_txs:
            print(f"\n✅ Jupiter Perps/Multiply 交易 ({len(multiply_txs)} 笔):")
            for tx in multiply_txs[:5]:
                print(f"\n   交易: {tx['signature'][:40]}...")
                for change in tx["changes"]:
                    if change.get("is_target"):
                        symbol = "+" if change["change"] > 0 else ""
                        print(f"   代币变化: {change['token']} {symbol}{change['change']:.6f}")
        
        if not kamino_txs and not lending_txs and not multiply_txs:
            print("\n❌ 在最近 50 笔交易中未发现借贷/杠杆相关活动")
            print("   该地址可能:")
            print("   1. 从未使用过 Jupiter Multiply")
            print("   2. 使用时间较早，超出查询范围")
            print("   3. 使用的是其他钱包地址")
        
        # 显示当前持仓
        print("\n" + "=" * 80)
        print("📋 当前持仓状态")
        print("=" * 80)
        
        # 获取代币余额
        payload = {
            "jsonrpc": "2.0",
            "method": "getTokenAccountsByOwner",
            "params": [
                TARGET_ADDRESS,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ],
            "id": 1
        }
        
        async with session.post(RPC_URL, json=payload) as response:
            data = await response.json()
            
            print("\n代币余额:")
            for account in data.get("result", {}).get("value", []):
                parsed = account["account"]["data"]["parsed"]["info"]
                mint = parsed["mint"]
                balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
                if balance > 0:
                    token_name = KNOWN_MINTS.get(mint, mint[:20] + "...")
                    print(f"   {token_name}: {balance:.6f}")
        
        # 获取 SOL 余额
        payload = {
            "jsonrpc": "2.0",
            "method": "getBalance",
            "params": [TARGET_ADDRESS],
            "id": 1
        }
        
        async with session.post(RPC_URL, json=payload) as response:
            data = await response.json()
            sol_balance = data.get("result", {}).get("value", 0) / 1e9
            print(f"   SOL: {sol_balance:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
