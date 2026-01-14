#!/usr/bin/env python3
"""
查询 Jupiter Multiply 仓位信息
jupSOL/SOL 循环借贷实际上是通过 Kamino 协议实现的
"""

import asyncio
import aiohttp
import json
from typing import Optional, Dict, Any

# 目标地址
TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"

# Solana RPC
RPC_URL = "https://api.mainnet-beta.solana.com"

# 已知的相关代币
KNOWN_TOKENS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "jupSOL",
    "So11111111111111111111111111111111111111112": "SOL (Wrapped)",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
}

# Kamino 相关 Program IDs
KAMINO_LENDING_PROGRAM = "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M"
KAMINO_FARMS_PROGRAM = "FarmsPZpWu9i7Kky8tPN37rs2TpmMrAZrC7S7vJa91Mo"

# Jupiter Multiply 可能使用的 Program
JUP_LIMIT_ORDER = "jupoNjAxXgZ4rjzxzPMP4oxduvQsQtZzyknqvzYNrNu"


async def get_sol_balance(session: aiohttp.ClientSession, address: str) -> float:
    """获取 SOL 余额"""
    payload = {
        "jsonrpc": "2.0",
        "method": "getBalance",
        "params": [address],
        "id": 1
    }
    
    async with session.post(RPC_URL, json=payload) as response:
        data = await response.json()
        if "result" in data:
            return data["result"]["value"] / 1e9
    return 0.0


async def get_token_accounts(session: aiohttp.ClientSession, address: str) -> list:
    """获取所有 SPL 代币账户"""
    payload = {
        "jsonrpc": "2.0",
        "method": "getTokenAccountsByOwner",
        "params": [
            address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ],
        "id": 1
    }
    
    async with session.post(RPC_URL, json=payload) as response:
        data = await response.json()
        if "result" in data:
            return data["result"].get("value", [])
    return []


async def get_program_accounts(session: aiohttp.ClientSession, program_id: str, filters: list = None) -> list:
    """获取 Program 账户"""
    params = [program_id, {"encoding": "jsonParsed"}]
    if filters:
        params[1]["filters"] = filters
    
    payload = {
        "jsonrpc": "2.0",
        "method": "getProgramAccounts",
        "params": params,
        "id": 1
    }
    
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
            data = await response.json()
            if "result" in data:
                return data["result"]
    except Exception as e:
        print(f"  ⚠️ 查询失败: {e}")
    return []


async def query_kamino_obligations(session: aiohttp.ClientSession, address: str) -> list:
    """查询 Kamino 借贷仓位 (Obligations)"""
    # Kamino Obligation 账户过滤器 - 按 owner 地址过滤
    # Obligation 账户结构中 owner 在 offset 32 位置
    from base58 import b58decode
    
    try:
        address_bytes = b58decode(address)
        address_base58 = address
        
        filters = [
            {"memcmp": {"offset": 32, "bytes": address_base58}}
        ]
        
        return await get_program_accounts(session, KAMINO_LENDING_PROGRAM, filters)
    except Exception as e:
        print(f"  ⚠️ Kamino 查询失败: {e}")
        return []


async def query_jupiter_api(session: aiohttp.ClientSession, address: str) -> Optional[dict]:
    """查询 Jupiter API 获取用户仓位"""
    # Jupiter 可能有专门的 API 端点
    urls = [
        f"https://api.jup.ag/accounts/{address}",
        f"https://perp.jup.ag/api/positions?wallet={address}",
        f"https://api.jup.ag/swap/v1/accounts/{address}",
    ]
    
    for url in urls:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        print(f"  ✅ 从 {url} 获取到数据")
                        return {"url": url, "data": data}
        except Exception as e:
            pass
    
    return None


async def query_kamino_api(session: aiohttp.ClientSession, address: str) -> Optional[dict]:
    """查询 Kamino API"""
    urls = [
        f"https://api.kamino.finance/users/{address}/obligations",
        f"https://api.hubbleprotocol.io/v2/kamino/users/{address}/obligations",
        f"https://api.hubbleprotocol.io/v2/kamino/users/{address}",
    ]
    
    for url in urls:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        print(f"  ✅ 从 {url} 获取到数据")
                        return {"url": url, "data": data}
        except Exception as e:
            pass
    
    return None


async def main():
    print("=" * 70)
    print(f"🔍 查询地址: {TARGET_ADDRESS}")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        # 1. 基本 SOL 余额
        print("\n📊 1. SOL 余额:")
        sol_balance = await get_sol_balance(session, TARGET_ADDRESS)
        print(f"   SOL: {sol_balance:.6f}")
        
        # 2. SPL 代币账户
        print("\n📊 2. SPL 代币账户:")
        token_accounts = await get_token_accounts(session, TARGET_ADDRESS)
        
        relevant_tokens = []
        for account in token_accounts:
            try:
                parsed = account["account"]["data"]["parsed"]["info"]
                mint = parsed["mint"]
                balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
                
                if balance > 0:
                    token_name = KNOWN_TOKENS.get(mint, mint[:12] + "...")
                    relevant_tokens.append({
                        "mint": mint,
                        "name": token_name,
                        "balance": balance
                    })
                    print(f"   {token_name}: {balance:.6f}")
            except Exception:
                continue
        
        if not relevant_tokens:
            print("   (无代币)")
        
        # 3. 查询 Jupiter API
        print("\n📊 3. 查询 Jupiter API...")
        jup_data = await query_jupiter_api(session, TARGET_ADDRESS)
        if jup_data:
            print(f"   数据: {json.dumps(jup_data['data'], indent=2)[:500]}...")
        else:
            print("   未找到 Jupiter 仓位数据")
        
        # 4. 查询 Kamino API
        print("\n📊 4. 查询 Kamino API (Jupiter Multiply 底层协议)...")
        kamino_data = await query_kamino_api(session, TARGET_ADDRESS)
        if kamino_data:
            print(f"   数据:")
            print(json.dumps(kamino_data['data'], indent=2))
        else:
            print("   未从 API 找到 Kamino 仓位数据")
        
        # 5. 直接查询链上 Kamino Program
        print("\n📊 5. 查询链上 Kamino 账户...")
        kamino_accounts = await query_kamino_obligations(session, TARGET_ADDRESS)
        if kamino_accounts:
            print(f"   找到 {len(kamino_accounts)} 个 Kamino 账户")
            for acc in kamino_accounts[:5]:
                print(f"   - {acc.get('pubkey', 'unknown')}")
        else:
            print("   未找到链上 Kamino 账户")
    
    print("\n" + "=" * 70)
    print("查询完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
