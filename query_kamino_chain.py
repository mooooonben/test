#!/usr/bin/env python3
"""
直接从链上查询 Kamino 借贷仓位
Jupiter Multiply 使用 Kamino 作为底层借贷协议
"""

import asyncio
import aiohttp
import json
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
RPC_URL = "https://api.mainnet-beta.solana.com"

# Kamino Lending Program
KAMINO_LENDING_PROGRAM = "KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M"

# 其他可能的 Program IDs
MARGINFI_PROGRAM = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"
SOLEND_PROGRAM = "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo"


async def get_account_info(session: aiohttp.ClientSession, address: str) -> dict:
    """获取账户信息"""
    payload = {
        "jsonrpc": "2.0",
        "method": "getAccountInfo",
        "params": [address, {"encoding": "base64"}],
        "id": 1
    }
    
    async with session.post(RPC_URL, json=payload) as response:
        data = await response.json()
        return data.get("result", {})


async def get_multiple_accounts(session: aiohttp.ClientSession, addresses: list) -> list:
    """批量获取账户信息"""
    payload = {
        "jsonrpc": "2.0",
        "method": "getMultipleAccounts",
        "params": [addresses, {"encoding": "base64"}],
        "id": 1
    }
    
    async with session.post(RPC_URL, json=payload) as response:
        data = await response.json()
        return data.get("result", {}).get("value", [])


async def find_program_accounts_by_owner(session: aiohttp.ClientSession, 
                                          program_id: str, 
                                          owner: str,
                                          offset: int = 32) -> list:
    """通过 owner 查找 Program 账户"""
    
    # 构建过滤器 - 在指定偏移量处匹配 owner 地址
    filters = [
        {
            "memcmp": {
                "offset": offset,
                "bytes": owner
            }
        }
    ]
    
    payload = {
        "jsonrpc": "2.0",
        "method": "getProgramAccounts",
        "params": [
            program_id,
            {
                "encoding": "base64",
                "filters": filters
            }
        ],
        "id": 1
    }
    
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            data = await response.json()
            if "error" in data:
                print(f"  RPC Error: {data['error']}")
                return []
            return data.get("result", [])
    except Exception as e:
        print(f"  查询失败: {e}")
        return []


async def find_all_program_accounts(session: aiohttp.ClientSession, 
                                     program_id: str,
                                     data_size: int = None) -> list:
    """获取所有 Program 账户 (带大小过滤)"""
    
    filters = []
    if data_size:
        filters.append({"dataSize": data_size})
    
    payload = {
        "jsonrpc": "2.0",
        "method": "getProgramAccounts",
        "params": [
            program_id,
            {
                "encoding": "base64",
                "filters": filters if filters else None
            }
        ],
        "id": 1
    }
    
    # 移除 None filters
    if not filters:
        del payload["params"][1]["filters"]
    
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
            data = await response.json()
            if "error" in data:
                print(f"  RPC Error: {data['error']}")
                return []
            return data.get("result", [])
    except Exception as e:
        print(f"  查询失败: {e}")
        return []


def try_parse_obligation(data_bytes: bytes, owner_address: str) -> dict:
    """尝试解析 Obligation 账户数据"""
    try:
        owner_bytes = b58decode(owner_address)
        
        # 在数据中查找 owner 地址
        for offset in [0, 8, 32, 40, 64, 72]:
            if offset + 32 <= len(data_bytes):
                potential_owner = data_bytes[offset:offset+32]
                if potential_owner == owner_bytes:
                    return {
                        "owner_found_at_offset": offset,
                        "data_length": len(data_bytes),
                        "first_64_bytes_hex": data_bytes[:64].hex()
                    }
        
        return None
    except Exception as e:
        return {"error": str(e)}


async def query_via_helius(session: aiohttp.ClientSession, address: str) -> dict:
    """尝试使用 Helius RPC (免费层)"""
    helius_urls = [
        "https://mainnet.helius-rpc.com/?api-key=demo",
    ]
    
    for helius_url in helius_urls:
        payload = {
            "jsonrpc": "2.0",
            "method": "getAssetsByOwner",
            "params": {
                "ownerAddress": address,
                "page": 1,
                "limit": 100
            },
            "id": 1
        }
        
        try:
            async with session.post(helius_url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result", {})
        except Exception as e:
            pass
    
    return {}


async def main():
    print("=" * 80)
    print(f"🔍 查询地址 Kamino 借贷仓位: {TARGET_ADDRESS}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 尝试不同的 offset 来查找 Kamino 账户
        print("\n📊 1. 查询 Kamino Lending Program 账户")
        print(f"   Program: {KAMINO_LENDING_PROGRAM}")
        
        # Kamino Obligation 账户结构中，owner 可能在不同位置
        offsets_to_try = [8, 32, 40, 64, 72, 104]
        
        found_accounts = []
        for offset in offsets_to_try:
            print(f"\n   尝试 offset={offset}...")
            accounts = await find_program_accounts_by_owner(
                session, 
                KAMINO_LENDING_PROGRAM, 
                TARGET_ADDRESS,
                offset=offset
            )
            if accounts:
                print(f"   ✅ 在 offset={offset} 找到 {len(accounts)} 个账户!")
                found_accounts.extend(accounts)
                for acc in accounts[:3]:
                    print(f"      - {acc['pubkey']}")
            else:
                print(f"   ❌ offset={offset} 未找到")
        
        # 2. 尝试 Marginfi
        print("\n📊 2. 查询 Marginfi Program 账户")
        print(f"   Program: {MARGINFI_PROGRAM}")
        
        for offset in [8, 32, 40]:
            accounts = await find_program_accounts_by_owner(
                session, 
                MARGINFI_PROGRAM, 
                TARGET_ADDRESS,
                offset=offset
            )
            if accounts:
                print(f"   ✅ 在 offset={offset} 找到 {len(accounts)} 个账户!")
                for acc in accounts[:3]:
                    print(f"      - {acc['pubkey']}")
                    # 解析账户数据
                    if acc.get("account", {}).get("data"):
                        data_b64 = acc["account"]["data"][0]
                        data_bytes = base64.b64decode(data_b64)
                        print(f"        数据长度: {len(data_bytes)} bytes")
        
        # 3. 检查代币账户的所有者关系
        print("\n📊 3. 分析代币账户")
        
        # 获取所有代币账户
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
            if "result" in data:
                for account in data["result"]["value"]:
                    parsed = account["account"]["data"]["parsed"]["info"]
                    mint = parsed["mint"]
                    balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
                    
                    # 检查是否是 jupSOL 或相关代币
                    if "jupSoL" in mint or balance > 0:
                        print(f"\n   代币: {mint[:20]}...")
                        print(f"   余额: {balance}")
                        print(f"   账户地址: {account['pubkey']}")
                        
                        # 获取该代币账户的详细信息
                        acc_info = await get_account_info(session, account['pubkey'])
                        if acc_info.get("value"):
                            owner = acc_info["value"].get("owner")
                            print(f"   账户 Owner Program: {owner}")
        
        # 4. 查看地址的所有交易签名
        print("\n📊 4. 查看最近交易")
        
        payload = {
            "jsonrpc": "2.0",
            "method": "getSignaturesForAddress",
            "params": [TARGET_ADDRESS, {"limit": 10}],
            "id": 1
        }
        
        async with session.post(RPC_URL, json=payload) as response:
            data = await response.json()
            if "result" in data:
                print(f"   最近 {len(data['result'])} 笔交易:")
                for sig in data["result"][:5]:
                    print(f"   - {sig['signature'][:30]}... (slot: {sig['slot']})")
        
        # 5. 汇总
        print("\n" + "=" * 80)
        print("📋 汇总")
        print("=" * 80)
        
        if found_accounts:
            print(f"\n✅ 找到 {len(found_accounts)} 个 Kamino 借贷账户")
            for acc in found_accounts:
                pubkey = acc['pubkey']
                if acc.get("account", {}).get("data"):
                    data_b64 = acc["account"]["data"][0]
                    data_bytes = base64.b64decode(data_b64)
                    print(f"\n   账户: {pubkey}")
                    print(f"   数据长度: {len(data_bytes)} bytes")
                    print(f"   前 64 字节: {data_bytes[:64].hex()}")
        else:
            print("\n❌ 未找到 Kamino 借贷仓位")
            print("   可能原因:")
            print("   1. 该地址没有活跃的 Kamino/Jupiter Multiply 仓位")
            print("   2. 仓位可能已经被平仓")
            print("   3. 使用的是其他借贷协议")


if __name__ == "__main__":
    asyncio.run(main())
