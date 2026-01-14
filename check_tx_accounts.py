#!/usr/bin/env python3
"""
检查交易中涉及的账户，找出仓位数据存储位置
"""

import asyncio
import aiohttp
import json
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"

# 从交易分析中发现的关键账户
TX_ACCOUNTS = [
    "HHQKhrDFtchP5Fk3Bu2GLXfsokPdf4qYuHpLe2gRmJqv",  # 可写账户 1
    "BxPMYFd7PnHE2tjH5KY2h3xcV8p6v8qHxPnkxpWZJxJ2",  # 可写账户 3
    "AjonqjVq34mDXzUKhUkNb5anqnd2BoY4Z1J7BshJpump",  # 可写账户 4
    "GR2nNXhsTMAZd4e8JbRJtCgkMdhKq4Gs2CmPHqFjHxuC",  # 可写账户 5
    "AWCKkAgmh8B2ERrTFwTP1UGfpK7XPX5pK2MEqHDPnFAw",  # 可写账户 6
    "5CF5844NpSr8GbdNdo7vARMFw27wbbtgBR5f87UHcz8q",  # 可写账户 7
    "J3ZGMcEExc7ceSV19M9tWnwZexgv7VLsxnMmwH6n3WDf",  # 可写账户 8
    "ALXWtv2P4GqH1B7Lq731joag52yRBRtBQLBYyRWkAhTU",  # 可写账户 16
    "4Y66HtUEqbbbpZdENGtFdVhUMS3tnaHqq2fvG9WmvZFP",  # 可写账户 17
    "BZZKgXxhxVkzx3NN8RfBPwU7ZmnQbDv8wgJKJU4vHNnT",  # 可写账户 18
    "5JP5zgYCb9W37QQLgAHRHuinFLrKt8Bzuc9puqz9TJTa",  # 可写账户 19
    "D8cy77BBepLMngZx6ZukaTff5hCt1HrWyKk3Hnd9oitf",  # 账户 12
    "D7UqeBmCEmhGXGYfi2y9RfoCa7t1XwK2AhmzNqzQ7TFC",  # 账户 15
]

# Jupiter Vault 相关程序
JUPITER_PROGRAMS = {
    "jupgfSgfuAXv4B6R2Uxu85Z1qdzgjuFcYL9RwV82j9e": "Jupiter Vault",
    "jupr81YtYssSyPt8jbnGuiWon5f6x9u7y6YBHD9kLvF": "Jupiter Router",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter V6",
}

RPC_URL = "https://api.mainnet-beta.solana.com"

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


async def get_account_info(session: aiohttp.ClientSession, address: str) -> dict:
    """获取账户信息"""
    result = await rpc_call(session, "getAccountInfo", [address, {"encoding": "base64"}])
    return result.get("result", {})


def analyze_account_data(data_bytes: bytes, account_address: str) -> dict:
    """分析账户数据"""
    info = {
        "address": account_address,
        "data_length": len(data_bytes),
    }
    
    if len(data_bytes) < 8:
        return info
    
    info["discriminator"] = data_bytes[:8].hex()
    
    # 查找 target address
    try:
        target_bytes = b58decode(TARGET_ADDRESS)
        if target_bytes in data_bytes:
            pos = data_bytes.find(target_bytes)
            info["target_address_at"] = pos
    except:
        pass
    
    # 查找 NFT mint
    try:
        nft_bytes = b58decode(NFT_MINT)
        if nft_bytes in data_bytes:
            pos = data_bytes.find(nft_bytes)
            info["nft_mint_at"] = pos
    except:
        pass
    
    # 查找已知 mints
    for mint_str, (name, decimals) in KNOWN_MINTS.items():
        try:
            mint_bytes = b58decode(mint_str)
            if mint_bytes in data_bytes:
                pos = data_bytes.find(mint_bytes)
                info[f"{name}_at"] = pos
        except:
            pass
    
    # 尝试解析 u64 数值
    amounts = []
    for offset in range(8, min(len(data_bytes) - 8, 500), 8):
        try:
            value = struct.unpack('<Q', data_bytes[offset:offset+8])[0]
            if 100_000 < value < 10_000_000_000_000_000:  # 合理范围
                readable = value / 10**9
                if 0.0001 < readable < 1_000_000:
                    amounts.append((offset, readable, value))
        except:
            pass
    
    if amounts:
        info["amounts"] = amounts[:15]
    
    return info


async def main():
    print("=" * 80)
    print(f"🔍 检查交易涉及的账户")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        position_candidates = []
        
        for address in TX_ACCOUNTS:
            print(f"\n📋 账户: {address}")
            
            info = await get_account_info(session, address)
            
            if info.get("value"):
                owner = info["value"].get("owner")
                data = info["value"].get("data", [])
                
                print(f"   Owner: {owner}")
                
                if data and data[0]:
                    data_bytes = base64.b64decode(data[0])
                    analysis = analyze_account_data(data_bytes, address)
                    
                    print(f"   数据长度: {analysis['data_length']} bytes")
                    print(f"   Discriminator: {analysis.get('discriminator', 'N/A')}")
                    
                    # 检查是否包含关键数据
                    is_position = False
                    
                    if "target_address_at" in analysis:
                        print(f"   ✅ 找到用户地址! offset: {analysis['target_address_at']}")
                        is_position = True
                    
                    if "nft_mint_at" in analysis:
                        print(f"   ✅ 找到 NFT Mint! offset: {analysis['nft_mint_at']}")
                        is_position = True
                    
                    if "jupSOL_at" in analysis:
                        print(f"   ✅ 找到 jupSOL! offset: {analysis['jupSOL_at']}")
                        is_position = True
                    
                    if "wSOL_at" in analysis:
                        print(f"   ✅ 找到 wSOL! offset: {analysis['wSOL_at']}")
                        is_position = True
                    
                    if is_position:
                        position_candidates.append({
                            "address": address,
                            "owner": owner,
                            "analysis": analysis
                        })
                        
                        # 显示可能的数量
                        if "amounts" in analysis:
                            print(f"   可能的数量值:")
                            for offset, readable, raw in analysis["amounts"][:8]:
                                print(f"      offset {offset}: {readable:.6f} ({raw})")
                else:
                    print(f"   (无数据或账户为空)")
            else:
                print(f"   ❌ 账户不存在或无法访问")
            
            await asyncio.sleep(0.3)
        
        # 汇总
        print("\n" + "=" * 80)
        print("📋 仓位候选账户")
        print("=" * 80)
        
        if position_candidates:
            print(f"\n找到 {len(position_candidates)} 个可能的仓位账户:")
            
            for candidate in position_candidates:
                print(f"\n   📋 {candidate['address']}")
                print(f"      Owner Program: {candidate['owner']}")
                
                analysis = candidate['analysis']
                
                # 这可能就是仓位账户！
                if "target_address_at" in analysis and "nft_mint_at" in analysis:
                    print(f"      ⭐ 这很可能是仓位账户!")
                    print(f"      用户地址位置: {analysis['target_address_at']}")
                    print(f"      NFT Mint 位置: {analysis['nft_mint_at']}")
                    
                    if "amounts" in analysis:
                        print(f"      仓位数据:")
                        for offset, readable, raw in analysis["amounts"][:5]:
                            print(f"         offset {offset}: {readable:.9f}")
        else:
            print("\n   未找到明确的仓位账户")


if __name__ == "__main__":
    asyncio.run(main())
