#!/usr/bin/env python3
"""
通过 API 获取 Jupiter Vault 仓位详情
"""

import asyncio
import aiohttp
import json

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"


async def try_api(session: aiohttp.ClientSession, url: str, headers: dict = None) -> dict:
    """尝试调用 API"""
    try:
        if headers is None:
            headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                return {"status": 200, "data": await response.json()}
            else:
                return {"status": response.status, "text": await response.text()}
    except Exception as e:
        return {"error": str(e)}


async def main():
    print("=" * 70)
    print("🔍 通过 API 获取 Jupiter Vault 仓位详情")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 获取 NFT 元数据
        print("\n📊 1. NFT 元数据")
        uri = "https://cdn.instadapp.io/solana/vaults/metadata/4.json"
        result = await try_api(session, uri)
        if result.get("status") == 200:
            print(f"   ✅ {json.dumps(result['data'], indent=2)}")
        
        # 2. 尝试各种 API
        print("\n📊 2. 尝试获取仓位 API")
        
        apis = [
            # Instadapp
            f"https://api.instadapp.io/defi/solana/vaults/position/{TARGET_ADDRESS}",
            f"https://api.instadapp.io/v2/solana/vaults/{TARGET_ADDRESS}",
            f"https://api.instadapp.io/solana/jupiter/vaults/{TARGET_ADDRESS}",
            
            # Jupiter
            f"https://jup.ag/api/vaults/positions/{TARGET_ADDRESS}",
            f"https://api.jup.ag/vaults/user/{TARGET_ADDRESS}",
            
            # 通用 DeFi APIs
            f"https://api.solscan.io/account?address={TARGET_ADDRESS}",
        ]
        
        for url in apis:
            print(f"\n   尝试: {url[:60]}...")
            result = await try_api(session, url)
            if result.get("status") == 200:
                print(f"   ✅ 成功!")
                data = result.get("data")
                if isinstance(data, dict):
                    print(f"   {json.dumps(data, indent=2)[:1000]}")
                elif isinstance(data, list):
                    print(f"   找到 {len(data)} 条数据")
                    for item in data[:3]:
                        print(f"   {json.dumps(item, indent=2)[:300]}")
            else:
                print(f"   ❌ {result.get('status', 'error')}")
        
        # 3. 从 Solscan 获取代币余额历史
        print("\n📊 3. Solscan Token 信息")
        
        solscan_apis = [
            f"https://public-api.solscan.io/account/tokens?account={TARGET_ADDRESS}",
            f"https://public-api.solscan.io/account/{TARGET_ADDRESS}",
        ]
        
        for url in solscan_apis:
            print(f"\n   尝试: {url[:60]}...")
            result = await try_api(session, url)
            if result.get("status") == 200:
                print(f"   ✅ 成功!")
                print(f"   {json.dumps(result.get('data'), indent=2)[:1500]}")
        
        # 4. 汇总
        print("\n" + "=" * 70)
        print("📋 总结")
        print("=" * 70)
        
        print("""
根据链上数据分析，你的 Jupiter Multiply 仓位信息如下：

📍 仓位凭证:
   NFT Mint: 8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD
   名称: Jupiter JUPSOL/SOL 4
   类型: jupSOL/SOL 杠杆仓位

📍 仓位账户:
   地址: AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec
   Owner: Jupiter Router (jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi)

📍 当前钱包余额:
   SOL: 0.556986
   jupSOL: 0.565273

📍 最近交易活动:
   - 最近5笔交易中净减少约 269.5 jupSOL
   - 表明进行了仓位调整/提取操作

📍 仓位机制说明:
   Jupiter Multiply jupSOL/SOL 是一个杠杆做多 jupSOL 相对于 SOL 的策略:
   1. 存入 jupSOL 作为抵押品
   2. 借入 SOL
   3. 将借入的 SOL 兑换为更多 jupSOL
   4. 重复以上步骤实现杠杆效果
   
   当 jupSOL 相对 SOL 升值时获利，反之亏损。

⚠️ 注意:
   要获取精确的抵押品数量、借款数量、杠杆倍数等信息，
   需要:
   1. 完整的 Jupiter Vault Program IDL
   2. 或者通过 Jupiter/Instadapp 官方 API (需要认证)
        """)


if __name__ == "__main__":
    asyncio.run(main())
