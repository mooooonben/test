#!/usr/bin/env python3
"""
查询 Jupiter Vault 仓位
基于交易分析发现的 Program IDs
"""

import asyncio
import aiohttp
import json
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"

RPC_URL = "https://api.mainnet-beta.solana.com"

# 从交易分析发现的 Jupiter 相关 Program
JUPITER_VAULT_PROGRAMS = [
    ("jupgfSgfuAXv4B6R2Uxu85Z1qdzgjuFcYL9RwV82j9e", "Jupiter Vault Main"),
    ("jupr81YtYssSyPt8jbnGuiWon5f6x9u7y6YBHD9kLvF", "Jupiter Vault Router"),
]

# 已知 mints
KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": ("jupSOL", 9),
    "So11111111111111111111111111111111111111112": ("wSOL", 9),
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    """调用 RPC"""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def search_program_accounts(session: aiohttp.ClientSession, program_id: str, 
                                   search_bytes: str, offsets: list) -> list:
    """搜索 Program 账户"""
    found = []
    
    for offset in offsets:
        result = await rpc_call(session, "getProgramAccounts", [
            program_id,
            {
                "encoding": "base64",
                "filters": [
                    {"memcmp": {"offset": offset, "bytes": search_bytes}}
                ]
            }
        ])
        
        if "error" not in result:
            accounts = result.get("result", [])
            if accounts:
                for acc in accounts:
                    found.append({
                        "pubkey": acc["pubkey"],
                        "offset": offset,
                        "data": acc["account"]["data"][0] if acc.get("account", {}).get("data") else None
                    })
        
        await asyncio.sleep(0.5)
    
    return found


def parse_vault_position(data_bytes: bytes) -> dict:
    """解析 Vault 仓位数据"""
    info = {
        "data_length": len(data_bytes),
        "discriminator": data_bytes[:8].hex() if len(data_bytes) >= 8 else ""
    }
    
    # 查找 mint 地址
    for mint_str, (name, decimals) in KNOWN_MINTS.items():
        mint_bytes = b58decode(mint_str)
        if mint_bytes in data_bytes:
            pos = data_bytes.find(mint_bytes)
            info[f"{name}_mint_at"] = pos
    
    # 查找 NFT mint
    try:
        nft_bytes = b58decode(NFT_MINT)
        if nft_bytes in data_bytes:
            pos = data_bytes.find(nft_bytes)
            info["nft_mint_at"] = pos
    except:
        pass
    
    # 查找 owner
    try:
        owner_bytes = b58decode(TARGET_ADDRESS)
        if owner_bytes in data_bytes:
            pos = data_bytes.find(owner_bytes)
            info["owner_at"] = pos
    except:
        pass
    
    # 尝试解析数值 (u64)
    potential_amounts = []
    for offset in range(8, min(len(data_bytes) - 8, 400), 8):
        try:
            value = struct.unpack('<Q', data_bytes[offset:offset+8])[0]
            # 合理的代币数量范围 (0.001 到 1000000 个代币，假设 9 decimals)
            if 1_000_000 < value < 1_000_000_000_000_000:
                readable = value / 10**9
                potential_amounts.append((offset, readable))
        except:
            pass
    
    if potential_amounts:
        info["potential_amounts"] = potential_amounts[:10]  # 只取前10个
    
    return info


async def main():
    print("=" * 80)
    print(f"🔍 查询 Jupiter Vault 仓位")
    print(f"   地址: {TARGET_ADDRESS}")
    print(f"   NFT: {NFT_MINT}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        all_found = []
        
        # 搜索 Jupiter Vault 程序
        for program_id, program_name in JUPITER_VAULT_PROGRAMS:
            print(f"\n{'='*60}")
            print(f"📊 搜索 {program_name}")
            print(f"   Program: {program_id}")
            print("=" * 60)
            
            # 用 NFT mint 搜索
            print("\n   用 NFT Mint 搜索:")
            offsets = [0, 8, 32, 40, 64, 72, 104, 136, 168, 200]
            accounts = await search_program_accounts(session, program_id, NFT_MINT, offsets)
            
            if accounts:
                print(f"   ✅ 找到 {len(accounts)} 个账户!")
                all_found.extend(accounts)
            else:
                print("   未找到")
            
            # 用 owner 搜索
            print("\n   用 Owner 地址搜索:")
            accounts = await search_program_accounts(session, program_id, TARGET_ADDRESS, offsets)
            
            if accounts:
                print(f"   ✅ 找到 {len(accounts)} 个账户!")
                for acc in accounts:
                    if acc["pubkey"] not in [a["pubkey"] for a in all_found]:
                        all_found.append(acc)
            else:
                print("   未找到")
        
        # 解析找到的账户
        print("\n" + "=" * 80)
        print("📋 解析仓位数据")
        print("=" * 80)
        
        if all_found:
            for acc in all_found:
                print(f"\n   📋 账户: {acc['pubkey']}")
                print(f"      找到位置 offset: {acc['offset']}")
                
                if acc.get("data"):
                    data_bytes = base64.b64decode(acc["data"])
                    parsed = parse_vault_position(data_bytes)
                    
                    print(f"      数据长度: {parsed['data_length']} bytes")
                    print(f"      Discriminator: {parsed['discriminator']}")
                    
                    if "nft_mint_at" in parsed:
                        print(f"      NFT Mint 位置: {parsed['nft_mint_at']}")
                    if "owner_at" in parsed:
                        print(f"      Owner 位置: {parsed['owner_at']}")
                    if "jupSOL_mint_at" in parsed:
                        print(f"      jupSOL Mint 位置: {parsed['jupSOL_mint_at']}")
                    if "wSOL_mint_at" in parsed:
                        print(f"      wSOL Mint 位置: {parsed['wSOL_mint_at']}")
                    
                    if "potential_amounts" in parsed:
                        print(f"      可能的数量值:")
                        for offset, amount in parsed["potential_amounts"]:
                            print(f"         offset {offset}: {amount:.6f}")
        else:
            print("\n   ❌ 未找到任何仓位账户")
            
            # 尝试获取账户列表（不带过滤器，看看结构）
            print("\n   尝试获取程序账户样本...")
            
            for program_id, program_name in JUPITER_VAULT_PROGRAMS:
                result = await rpc_call(session, "getProgramAccounts", [
                    program_id,
                    {
                        "encoding": "base64",
                        "dataSlice": {"offset": 0, "length": 100}  # 只获取前100字节
                    }
                ])
                
                if "error" not in result:
                    accounts = result.get("result", [])
                    print(f"\n   {program_name} 共有 {len(accounts)} 个账户")
                    
                    if accounts:
                        # 分析账户结构
                        print("   样本账户:")
                        for acc in accounts[:3]:
                            pubkey = acc["pubkey"]
                            data = base64.b64decode(acc["account"]["data"][0]) if acc.get("account", {}).get("data") else b""
                            print(f"      - {pubkey[:30]}...")
                            print(f"        前64字节: {data[:64].hex()}")


if __name__ == "__main__":
    asyncio.run(main())
