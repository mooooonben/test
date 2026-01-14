#!/usr/bin/env python3
"""
获取 Jupiter Multiply 仓位详细信息
基于 NFT 凭证查找关联的仓位数据
"""

import asyncio
import aiohttp
import json
import base64
from base58 import b58decode, b58encode
import struct

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"

RPC_URL = "https://api.mainnet-beta.solana.com"

# 已知代币
KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": ("jupSOL", 9),
    "So11111111111111111111111111111111111111112": ("SOL", 9),
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": ("JitoSOL", 9),
}

# 可能的 Program IDs
PROGRAMS_TO_CHECK = [
    ("6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc", "Kamino Farms/Multiply"),
    ("KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M", "Kamino Lending"),
    ("kvauTFR8qm1dhniz6pYuBZkuene3Hfrs1VQhVRgCNrr", "Kamino Vault"),
    ("MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA", "Marginfi"),
    ("E6qbhrt4pFmCotNUSSa6G4F1XUvy4xB12Bev8LWFBCN8", "Instadapp"),
]


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list, timeout: int = 30) -> dict:
    """调用 RPC"""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def find_accounts_with_nft(session: aiohttp.ClientSession, program_id: str, nft_mint: str) -> list:
    """查找包含 NFT mint 的账户"""
    found = []
    
    # 尝试不同的 offset
    offsets = [0, 8, 32, 40, 64, 72, 96, 104, 128, 136, 160, 168, 192, 200]
    
    for offset in offsets:
        result = await rpc_call(session, "getProgramAccounts", [
            program_id,
            {
                "encoding": "base64",
                "filters": [
                    {"memcmp": {"offset": offset, "bytes": nft_mint}}
                ]
            }
        ])
        
        accounts = result.get("result", [])
        if accounts:
            for acc in accounts:
                found.append({
                    "pubkey": acc["pubkey"],
                    "program": program_id,
                    "offset": offset,
                    "data": acc["account"]["data"][0] if acc.get("account", {}).get("data") else None,
                    "owner": acc.get("account", {}).get("owner")
                })
        
        await asyncio.sleep(0.3)
    
    return found


async def find_accounts_with_owner(session: aiohttp.ClientSession, program_id: str, owner: str) -> list:
    """查找属于特定 owner 的账户"""
    found = []
    
    offsets = [8, 32, 40, 64, 72, 104]
    
    for offset in offsets:
        result = await rpc_call(session, "getProgramAccounts", [
            program_id,
            {
                "encoding": "base64",
                "filters": [
                    {"memcmp": {"offset": offset, "bytes": owner}}
                ]
            }
        ])
        
        accounts = result.get("result", [])
        if accounts:
            for acc in accounts:
                found.append({
                    "pubkey": acc["pubkey"],
                    "program": program_id,
                    "offset": offset,
                    "data": acc["account"]["data"][0] if acc.get("account", {}).get("data") else None,
                    "owner": acc.get("account", {}).get("owner")
                })
        
        await asyncio.sleep(0.3)
    
    return found


async def get_account_info(session: aiohttp.ClientSession, address: str) -> dict:
    """获取账户信息"""
    result = await rpc_call(session, "getAccountInfo", [address, {"encoding": "base64"}])
    return result.get("result", {})


def try_parse_position_data(data_bytes: bytes) -> dict:
    """尝试解析仓位数据"""
    info = {
        "data_length": len(data_bytes),
        "hex_preview": data_bytes[:128].hex() if len(data_bytes) >= 128 else data_bytes.hex()
    }
    
    # 尝试找到已知的 mint 地址
    for mint_str, (name, decimals) in KNOWN_MINTS.items():
        mint_bytes = b58decode(mint_str)
        if mint_bytes in data_bytes:
            pos = data_bytes.find(mint_bytes)
            info[f"found_{name}_at"] = pos
    
    # 尝试解析一些常见的数值
    try:
        # 假设前8字节是 discriminator
        if len(data_bytes) >= 8:
            info["discriminator"] = data_bytes[:8].hex()
        
        # 尝试在不同位置找 u64 数值 (可能是余额)
        for offset in [8, 40, 72, 104, 136, 168, 200, 232]:
            if offset + 8 <= len(data_bytes):
                value = struct.unpack('<Q', data_bytes[offset:offset+8])[0]
                if value > 0 and value < 10**18:  # 合理的代币数量
                    # 转换为可读数字 (假设 9 decimals)
                    readable = value / 10**9
                    if readable > 0.0001:
                        info[f"u64_at_{offset}"] = f"{readable:.6f}"
    except:
        pass
    
    return info


async def query_instadapp_api(session: aiohttp.ClientSession, address: str) -> dict:
    """查询 Instadapp API"""
    urls = [
        f"https://api.instadapp.io/v2/solana/vaults/positions?owner={address}",
        f"https://api.instadapp.io/solana/vaults/{address}",
    ]
    
    for url in urls:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                   headers={"Accept": "application/json"}) as response:
                if response.status == 200:
                    return {"url": url, "data": await response.json()}
        except:
            pass
    
    return {}


async def main():
    print("=" * 80)
    print(f"🔍 获取 Jupiter Multiply 仓位详情")
    print(f"   地址: {TARGET_ADDRESS}")
    print(f"   NFT Mint: {NFT_MINT}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 先获取 NFT 的更多信息
        print("\n📊 1. NFT 账户信息")
        
        nft_info = await get_account_info(session, NFT_MINT)
        if nft_info.get("value"):
            owner = nft_info["value"].get("owner")
            print(f"   NFT Mint Owner Program: {owner}")
            
            # 如果是 Token-2022 或其他特殊程序
            if owner != "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
                print(f"   ⚠️ 使用非标准 Token Program!")
        
        # 2. 尝试 Instadapp API
        print("\n📊 2. 查询 Instadapp API")
        
        instadapp_data = await query_instadapp_api(session, TARGET_ADDRESS)
        if instadapp_data:
            print(f"\n   ✅ 从 API 获取到数据:")
            print(json.dumps(instadapp_data, indent=2, ensure_ascii=False)[:2000])
        else:
            print("   ❌ Instadapp API 未返回数据")
        
        # 3. 搜索各个 Program
        print("\n📊 3. 搜索关联的 Program 账户")
        
        all_found = []
        
        for program_id, program_name in PROGRAMS_TO_CHECK:
            print(f"\n   检查 {program_name} ({program_id[:16]}...)...")
            
            # 用 NFT mint 搜索
            accounts = await find_accounts_with_nft(session, program_id, NFT_MINT)
            if accounts:
                print(f"   ✅ 用 NFT 找到 {len(accounts)} 个账户!")
                all_found.extend(accounts)
            
            # 用 owner 搜索
            owner_accounts = await find_accounts_with_owner(session, program_id, TARGET_ADDRESS)
            if owner_accounts:
                print(f"   ✅ 用 Owner 找到 {len(owner_accounts)} 个账户!")
                # 去重
                existing_pubkeys = {a["pubkey"] for a in all_found}
                for acc in owner_accounts:
                    if acc["pubkey"] not in existing_pubkeys:
                        all_found.append(acc)
            
            await asyncio.sleep(0.5)
        
        # 4. 解析找到的账户
        print("\n" + "=" * 40)
        print("📊 4. 解析仓位账户数据")
        print("=" * 40)
        
        if all_found:
            print(f"\n   共找到 {len(all_found)} 个相关账户:")
            
            for acc in all_found:
                print(f"\n   📋 账户: {acc['pubkey']}")
                print(f"      Program: {acc['program'][:20]}...")
                print(f"      Offset: {acc['offset']}")
                
                if acc.get("data"):
                    data_bytes = base64.b64decode(acc["data"])
                    parsed = try_parse_position_data(data_bytes)
                    
                    print(f"      数据长度: {parsed['data_length']} bytes")
                    print(f"      Discriminator: {parsed.get('discriminator', 'N/A')}")
                    
                    # 显示找到的代币位置
                    for key, value in parsed.items():
                        if key.startswith("found_"):
                            print(f"      {key}: offset {value}")
                        elif key.startswith("u64_at_"):
                            print(f"      {key}: {value}")
        else:
            print("\n   ❌ 未找到关联账户")
        
        # 5. 尝试查看最近的交易来理解仓位
        print("\n" + "=" * 40)
        print("📊 5. 分析最近涉及 NFT 的交易")
        print("=" * 40)
        
        # 获取 NFT token account
        result = await rpc_call(session, "getTokenAccountsByOwner", [
            TARGET_ADDRESS,
            {"mint": NFT_MINT},
            {"encoding": "jsonParsed"}
        ])
        
        nft_accounts = result.get("result", {}).get("value", [])
        if nft_accounts:
            nft_token_account = nft_accounts[0]["pubkey"]
            print(f"   NFT Token Account: {nft_token_account}")
            
            # 获取该账户的交易
            result = await rpc_call(session, "getSignaturesForAddress", [
                nft_token_account,
                {"limit": 5}
            ])
            
            signatures = result.get("result", [])
            if signatures:
                print(f"\n   最近 {len(signatures)} 笔交易:")
                for sig in signatures:
                    print(f"   - {sig['signature'][:40]}... (slot: {sig['slot']})")
        
        # 6. 汇总
        print("\n" + "=" * 80)
        print("📋 汇总")
        print("=" * 80)
        
        print(f"""
NFT 仓位凭证:
- Mint: {NFT_MINT}
- 名称: Jupiter JUPSOL/SOL 4
- 类型: Jupiter Lend vault 4

这个 NFT 代表一个 jupSOL/SOL 的杠杆仓位。
仓位的实际数据可能存储在与 NFT 关联的 PDA 账户中。

找到的关联账户数: {len(all_found)}
        """)


if __name__ == "__main__":
    asyncio.run(main())
