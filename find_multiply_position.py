#!/usr/bin/env python3
"""
更全面地查找 Jupiter Multiply 仓位
"""

import asyncio
import aiohttp
import json
import base64
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"

# 使用更稳定的 RPC
RPC_URLS = [
    "https://rpc.ankr.com/solana",
    "https://api.mainnet-beta.solana.com",
]

# 所有可能相关的 Program IDs
PROGRAMS = {
    # Kamino 相关
    "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M": "Kamino Lending",
    "kvauTFR8qm1dhniz6pYuBZkuene3Hfrs1VQhVRgCNrr": "Kamino Vault",
    "6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc": "Kamino Farms",
    "FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn": "Kamino Flash",
    
    # Marginfi
    "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA": "Marginfi V2",
    
    # Solend
    "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo": "Solend",
    
    # Jupiter
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter V6",
    "PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu": "Jupiter Perps",
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list, timeout: int = 60) -> dict:
    """调用 RPC"""
    for rpc_url in RPC_URLS:
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": 1
            }
            async with session.post(rpc_url, json=payload, 
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                data = await response.json()
                if "error" not in data:
                    return data
                else:
                    print(f"   RPC Error ({rpc_url}): {data.get('error', {}).get('message', '')[:50]}")
        except Exception as e:
            print(f"   Exception ({rpc_url}): {str(e)[:50]}")
            continue
    return {}


async def find_accounts_by_owner(session: aiohttp.ClientSession, program_id: str, owner: str) -> list:
    """通过 owner 查找账户，尝试多个 offset"""
    results = []
    
    # Kamino Obligation 结构中 owner 可能在这些位置
    # 尝试多个常见的 offset
    offsets = [8, 32, 40, 48, 64, 72, 80, 96, 104, 112, 128]
    
    for offset in offsets:
        try:
            result = await rpc_call(session, "getProgramAccounts", [
                program_id,
                {
                    "encoding": "base64",
                    "filters": [
                        {"memcmp": {"offset": offset, "bytes": owner}}
                    ]
                }
            ], timeout=30)
            
            accounts = result.get("result", [])
            if accounts:
                print(f"   ✅ 在 offset={offset} 找到 {len(accounts)} 个账户!")
                for acc in accounts:
                    results.append({
                        "pubkey": acc["pubkey"],
                        "offset": offset,
                        "data": acc["account"]["data"][0] if acc.get("account", {}).get("data") else None,
                        "program": program_id
                    })
        except Exception as e:
            pass
        
        await asyncio.sleep(0.5)  # 避免限流
    
    return results


async def get_account_info(session: aiohttp.ClientSession, address: str) -> dict:
    """获取账户信息"""
    result = await rpc_call(session, "getAccountInfo", [
        address, 
        {"encoding": "jsonParsed"}
    ])
    return result.get("result", {})


async def get_all_token_accounts(session: aiohttp.ClientSession, address: str) -> list:
    """获取所有代币账户，包括 Token-2022"""
    accounts = []
    
    # Token Program
    result = await rpc_call(session, "getTokenAccountsByOwner", [
        address,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"}
    ])
    accounts.extend(result.get("result", {}).get("value", []))
    
    # Token-2022 Program
    result = await rpc_call(session, "getTokenAccountsByOwner", [
        address,
        {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"},
        {"encoding": "jsonParsed"}
    ])
    accounts.extend(result.get("result", {}).get("value", []))
    
    return accounts


async def search_all_related_accounts(session: aiohttp.ClientSession, address: str) -> list:
    """搜索所有相关账户"""
    all_accounts = []
    
    # 获取该地址拥有的所有账户
    result = await rpc_call(session, "getProgramAccounts", [
        "11111111111111111111111111111111",  # System Program - 不会返回太多
        {
            "encoding": "base64",
            "filters": [
                {"memcmp": {"offset": 0, "bytes": address}}
            ]
        }
    ])
    
    return all_accounts


async def check_specific_kamino_markets(session: aiohttp.ClientSession, address: str):
    """检查特定的 Kamino 市场"""
    
    # Kamino 主要市场地址 (这些是已知的 Kamino lending markets)
    kamino_markets = [
        "7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF",  # Main Market
        "DxXdAyU3kCjnyggvHmY5nAwg5cRbbmdyX3npfDMjjMek",  # JLP Market
        "ByYiZxp8QrdN9qbdtaAiePN8AAr3qvTPppNJDpf5DVJ5",  # Altcoins Market
    ]
    
    print("\n📊 检查 Kamino 特定市场...")
    
    for market in kamino_markets:
        print(f"\n   检查市场: {market[:20]}...")
        
        # 尝试查找该用户在此市场的 obligation
        # Kamino obligation 的 PDA 通常由 market + user 生成
        
        # 直接搜索
        result = await rpc_call(session, "getProgramAccounts", [
            PROGRAMS.get("KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M", "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M"),
            {
                "encoding": "base64",
                "filters": [
                    {"memcmp": {"offset": 32, "bytes": address}},  # owner at offset 32
                    {"memcmp": {"offset": 8, "bytes": market}}     # market at offset 8
                ]
            }
        ], timeout=30)
        
        accounts = result.get("result", [])
        if accounts:
            print(f"   ✅ 找到 {len(accounts)} 个账户!")
            return accounts
        
        await asyncio.sleep(0.5)
    
    return []


async def main():
    print("=" * 80)
    print(f"🔍 深入查找 Jupiter Multiply 仓位")
    print(f"   地址: {TARGET_ADDRESS}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 先获取基本信息
        print("\n📊 1. 基本余额信息")
        
        # SOL
        result = await rpc_call(session, "getBalance", [TARGET_ADDRESS])
        sol_balance = result.get("result", {}).get("value", 0) / 1e9
        print(f"   SOL: {sol_balance:.6f}")
        
        # 代币
        token_accounts = await get_all_token_accounts(session, TARGET_ADDRESS)
        print(f"\n   代币账户 ({len(token_accounts)} 个):")
        
        for acc in token_accounts:
            try:
                parsed = acc["account"]["data"]["parsed"]["info"]
                mint = parsed["mint"]
                balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
                decimals = parsed["tokenAmount"]["decimals"]
                if balance > 0:
                    print(f"   - {mint[:20]}... : {balance}")
            except:
                pass
        
        # 2. 查询 Kamino Lending 账户
        print("\n" + "=" * 40)
        print("📊 2. 查询 Kamino Lending 账户")
        print("=" * 40)
        
        kamino_program = "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M"
        
        print(f"\n   搜索用户的 Obligation 账户...")
        kamino_accounts = await find_accounts_by_owner(session, kamino_program, TARGET_ADDRESS)
        
        if kamino_accounts:
            print(f"\n   ✅ 找到 {len(kamino_accounts)} 个 Kamino 账户:")
            for acc in kamino_accounts:
                print(f"      - {acc['pubkey']} (offset: {acc['offset']})")
                
                # 尝试解析账户数据
                if acc.get('data'):
                    data_bytes = base64.b64decode(acc['data'])
                    print(f"        数据长度: {len(data_bytes)} bytes")
        
        # 3. 检查特定市场
        market_accounts = await check_specific_kamino_markets(session, TARGET_ADDRESS)
        
        # 4. 查询 Marginfi
        print("\n" + "=" * 40)
        print("📊 3. 查询 Marginfi 账户")
        print("=" * 40)
        
        marginfi_program = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"
        marginfi_accounts = await find_accounts_by_owner(session, marginfi_program, TARGET_ADDRESS)
        
        if marginfi_accounts:
            print(f"\n   ✅ 找到 {len(marginfi_accounts)} 个 Marginfi 账户")
        
        # 5. 尝试查询 Hubble API (Kamino 母公司)
        print("\n" + "=" * 40)
        print("📊 4. 查询 Hubble/Kamino API")
        print("=" * 40)
        
        hubble_urls = [
            f"https://api.hubbleprotocol.io/v2/kamino/users/{TARGET_ADDRESS}/obligations",
            f"https://api.hubbleprotocol.io/kamino/users/{TARGET_ADDRESS}/obligations", 
            f"https://api.hubbleprotocol.io/v2/kamino/obligations?owner={TARGET_ADDRESS}",
            f"https://api.kamino.finance/v2/users/{TARGET_ADDRESS}/obligations",
        ]
        
        for url in hubble_urls:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                       headers={"Accept": "application/json"}) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            print(f"\n   ✅ 从 API 获取到数据:")
                            print(f"   URL: {url}")
                            print(json.dumps(data, indent=2)[:2000])
                            break
                    else:
                        print(f"   {url[:50]}... -> {response.status}")
            except Exception as e:
                print(f"   {url[:50]}... -> Error: {str(e)[:30]}")
        
        # 6. 汇总
        print("\n" + "=" * 80)
        print("📋 汇总")
        print("=" * 80)
        
        total_found = len(kamino_accounts) + len(market_accounts) + len(marginfi_accounts)
        
        if total_found > 0:
            print(f"\n✅ 共找到 {total_found} 个借贷相关账户")
        else:
            print("\n❌ 未找到借贷仓位账户")
            print("\n   可能的原因:")
            print("   1. Jupiter Multiply 可能使用了不同的 Program 或账户结构")
            print("   2. 仓位可能存储在不同的市场中")
            print("   3. 需要更多的 offset 来查找")
            print("\n   建议:")
            print("   - 请确认这个地址是否真的有 Multiply 仓位")
            print("   - 可以在 Jupiter 网站查看仓位确认")


if __name__ == "__main__":
    asyncio.run(main())
