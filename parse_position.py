#!/usr/bin/env python3
"""
解析 Jupiter Multiply 仓位详细数据
"""

import asyncio
import aiohttp
import json
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"

# 发现的关键账户
POSITION_ACCOUNTS = [
    ("AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec", "NFT Position (包含 NFT Mint)"),
    ("5CF5844NpSr8GbdNdo7vARMFw27wbbzd6M2vfyLDrgu3", "Jupiter Router Account 1"),
    ("J3ZGMcEExc7ceSV19M9tWnwZexgv7Vk7meu6ziQgZsFM", "Jupiter Router Account 2"),
    ("9WoJAcLA7jcFRFTmLwYsGDJRg7FM8SL1bsqWEg9oyBXh", "Jupiter Router Account 3"),
    ("ETQGC3N6qUNbN7oojsxF41mSm1ePWZLomXEpHHBemnA1", "Jupiter Router Account 4"),
    ("ALXWtv2P4GqH1B7Lq731joag52yRBRqmHV4naiXPTYWL", "Jupiter Vault Account"),
    ("4Y66HtUEqbbbpZdENGtFdVhUMS3tnagffn3M4do59Nfy", "Jupiter Stake Pool Account 1"),
    ("BZZKgXxhxVkzx3NN8RfBPwU7ZmnQbDtp3ezcsXbiALL6", "Jupiter Stake Pool Account 2"),
    ("7HZhrUgLcHiQ8hkvNXM9gkM7CAeP21s478P8pHhANwns", "Jupiter Stake Pool Account 3"),
    ("9DiqWS3ooZHprymNuwxQ4PcjXHRBPjtAvvWEtrpSoaxT", "Jupiter Stake Pool Account 4"),
]

# 已知 mints
KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "jupSOL",
    "So11111111111111111111111111111111111111112": "wSOL",
    NFT_MINT: "Position NFT",
}

RPC_URL = "https://api.mainnet-beta.solana.com"


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


def parse_account_data(data_bytes: bytes, name: str) -> dict:
    """详细解析账户数据"""
    result = {
        "name": name,
        "length": len(data_bytes),
        "hex": data_bytes.hex(),
        "found_addresses": [],
        "found_amounts": []
    }
    
    if len(data_bytes) < 8:
        return result
    
    result["discriminator"] = data_bytes[:8].hex()
    
    # 查找所有 pubkey (32 bytes)
    for mint_str, mint_name in KNOWN_MINTS.items():
        try:
            mint_bytes = b58decode(mint_str)
            pos = 0
            while True:
                pos = data_bytes.find(mint_bytes, pos)
                if pos == -1:
                    break
                result["found_addresses"].append({
                    "name": mint_name,
                    "address": mint_str,
                    "offset": pos
                })
                pos += 1
        except:
            pass
    
    # 查找用户地址
    try:
        target_bytes = b58decode(TARGET_ADDRESS)
        pos = 0
        while True:
            pos = data_bytes.find(target_bytes, pos)
            if pos == -1:
                break
            result["found_addresses"].append({
                "name": "User Address",
                "address": TARGET_ADDRESS,
                "offset": pos
            })
            pos += 1
    except:
        pass
    
    # 解析 u64 数值 (可能是余额/数量)
    for offset in range(0, min(len(data_bytes) - 8, 500), 8):
        try:
            value = struct.unpack('<Q', data_bytes[offset:offset+8])[0]
            # 过滤合理的代币数量
            if 1_000_000 < value < 100_000_000_000_000_000:  # 0.001 - 100M tokens (9 decimals)
                readable = value / 10**9
                if 0.001 < readable < 100_000_000:
                    result["found_amounts"].append({
                        "offset": offset,
                        "raw": value,
                        "as_9_decimals": readable
                    })
        except:
            pass
    
    return result


async def main():
    print("=" * 80)
    print(f"🔍 解析 Jupiter Multiply 仓位数据")
    print(f"   用户: {TARGET_ADDRESS}")
    print(f"   NFT: {NFT_MINT}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        all_parsed = []
        
        for address, name in POSITION_ACCOUNTS:
            print(f"\n{'='*60}")
            print(f"📋 {name}")
            print(f"   地址: {address}")
            print("=" * 60)
            
            result = await rpc_call(session, "getAccountInfo", [address, {"encoding": "base64"}])
            
            if result.get("result", {}).get("value"):
                info = result["result"]["value"]
                owner = info.get("owner")
                data = info.get("data", [])
                
                print(f"   Owner: {owner}")
                
                if data and data[0]:
                    data_bytes = base64.b64decode(data[0])
                    parsed = parse_account_data(data_bytes, name)
                    all_parsed.append(parsed)
                    
                    print(f"   数据长度: {parsed['length']} bytes")
                    print(f"   Discriminator: {parsed['discriminator']}")
                    
                    if parsed["found_addresses"]:
                        print(f"\n   找到的地址:")
                        for addr in parsed["found_addresses"]:
                            print(f"      - {addr['name']} at offset {addr['offset']}")
                    
                    if parsed["found_amounts"]:
                        print(f"\n   找到的数量值:")
                        for amt in parsed["found_amounts"][:8]:
                            print(f"      offset {amt['offset']:3d}: {amt['as_9_decimals']:.9f} ({amt['raw']})")
                    
                    # 打印原始数据用于分析
                    print(f"\n   原始数据 (hex):")
                    hex_data = parsed["hex"]
                    for i in range(0, min(len(hex_data), 256), 64):
                        offset = i // 2
                        print(f"      {offset:3d}: {hex_data[i:i+64]}")
            else:
                print(f"   ❌ 账户不存在或为空")
            
            await asyncio.sleep(0.3)
        
        # 汇总分析
        print("\n" + "=" * 80)
        print("📋 仓位汇总分析")
        print("=" * 80)
        
        # 合并所有找到的金额
        all_amounts = []
        for parsed in all_parsed:
            for amt in parsed.get("found_amounts", []):
                all_amounts.append({
                    "account": parsed["name"],
                    "offset": amt["offset"],
                    "value": amt["as_9_decimals"]
                })
        
        # 按金额排序
        all_amounts.sort(key=lambda x: x["value"], reverse=True)
        
        print("\n   所有发现的数量值 (按大小排序):")
        for amt in all_amounts[:15]:
            print(f"   {amt['account'][:30]:30s} offset {amt['offset']:3d}: {amt['value']:.9f}")
        
        # 总结
        print("\n" + "=" * 80)
        print("📋 Jupiter Multiply 仓位信息来源")
        print("=" * 80)
        
        print("""
Jupiter Multiply jupSOL/SOL 仓位的数据存储结构：

1. **NFT 仓位凭证**
   - Mint: 8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD
   - 名称: Jupiter JUPSOL/SOL 4
   - 元数据 URI: https://cdn.instadapp.io/solana/vaults/metadata/4.json

2. **仓位账户**
   - AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec
   - Owner Program: jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi

3. **相关 Programs**
   - jupgfSgfuAXv4B6R2Uxu85Z1qdzgju79s6MfZekN6XS (Jupiter Vault)
   - jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi (Jupiter Router)
   - jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC (Jupiter Stake Pool)

4. **仓位数据获取方式**
   - 通过 NFT mint 在 Jupiter Router Program 中查找关联账户
   - 解析账户数据获取抵押品 (jupSOL) 和借款 (SOL) 信息
        """)


if __name__ == "__main__":
    asyncio.run(main())
