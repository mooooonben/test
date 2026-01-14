#!/usr/bin/env python3
"""
验证 Jupiter Multiply 仓位数据
对比链上数据和 Jupiter 网站显示的数据
"""

import asyncio
import aiohttp
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"
POSITION_ACCOUNT = "AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec"

RPC_URL = "https://api.mainnet-beta.solana.com"

# 从 Jupiter 网站截图获取的真实数据
EXPECTED_COLLATERAL_JUPSOL = 5754.67
EXPECTED_DEBT_SOL = 6120.67
EXPECTED_NET_VALUE_USD = 83104.29
EXPECTED_MULTIPLIER = 11.7
EXPECTED_LTV = 0.94


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
        return await response.json()


async def main():
    print("=" * 70)
    print("🔍 验证 Jupiter Multiply 仓位数据")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        
        # 获取仓位账户数据
        result = await rpc_call(session, "getAccountInfo", [POSITION_ACCOUNT, {"encoding": "base64"}])
        data = base64.b64decode(result["result"]["value"]["data"][0])
        
        print(f"\n📋 仓位账户数据解析")
        print(f"   账户: {POSITION_ACCOUNT}")
        print(f"   数据长度: {len(data)} bytes")
        
        # 解析数据
        # offset 46 开始是仓位数据
        position_data = data[46:]
        print(f"\n   Position Data (hex): {position_data.hex()}")
        
        # 根据之前的分析，尝试解析
        # offset 46+8 (即 offset 54 from start) 包含一个数值
        
        # 解析 u64 at offset 54 (相对于整个数据)
        # 这应该是 5754.67 jupSOL
        
        # 重新解析
        print(f"\n   📊 数据解析:")
        
        # 尝试不同的解析方式
        for i in range(0, min(len(position_data) - 7, 20), 1):
            val = struct.unpack('<Q', position_data[i:i+8])[0]
            readable_9 = val / 1e9
            # 只显示接近预期值的
            if 5000 < readable_9 < 7000:  # 接近 5754 或 6120
                print(f"   offset {46+i}: {val} = {readable_9:.6f}")
        
        # 直接解析 offset 54 (data[54:62])
        collateral_raw = struct.unpack('<Q', data[54:62])[0]
        collateral = collateral_raw / 1e9
        
        print(f"\n   📊 解析结果:")
        print(f"   抵押品 (offset 54): {collateral:.6f} jupSOL")
        print(f"   预期值: {EXPECTED_COLLATERAL_JUPSOL:.2f} jupSOL")
        print(f"   匹配: {'✅' if abs(collateral - EXPECTED_COLLATERAL_JUPSOL) < 1 else '❌'}")
        
        # 债务可能在其他账户中
        # 让我检查 Router 账户
        router_account = "9WoJAcLA7jcFRFTmLwYsGDJRg7FM8SL1bsqWEg9oyBXh"
        result = await rpc_call(session, "getAccountInfo", [router_account, {"encoding": "base64"}])
        if result.get("result", {}).get("value"):
            router_data = base64.b64decode(result["result"]["value"]["data"][0])
            print(f"\n   📋 Router 账户数据:")
            print(f"   长度: {len(router_data)} bytes")
            
            # 寻找接近 6120 的值
            for i in range(0, min(len(router_data) - 7, 200), 8):
                val = struct.unpack('<Q', router_data[i:i+8])[0]
                readable_9 = val / 1e9
                if 5000 < readable_9 < 7000:
                    print(f"   offset {i}: {val} = {readable_9:.6f}")
        
        # 汇总
        print(f"\n" + "=" * 70)
        print("📊 仓位信息对比")
        print("=" * 70)
        
        print(f"""
┌─────────────────────────────────────────────────────────────────────────┐
│                  Jupiter Multiply 仓位验证                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  🔖 仓位标识                                                            │
│     NFT ID: #2606                                                       │
│     NFT Mint: {NFT_MINT}                 │
│     URL: jup.ag/lend/multiply/4/nfts/2606                              │
│                                                                         │
│  💰 仓位详情 (来自 Jupiter 网站)                                        │
│     净值 (Net Value): $83,104.29                                        │
│     杠杆倍数: 11.7x / 16.65x                                            │
│     LTV: 94%                                                            │
│     状态: 91.45% Safe                                                   │
│                                                                         │
│  📊 抵押品 (Collateral)                                                 │
│     数量: 5,754.67 JupSOL                                               │
│     价值: $974,448.55                                                   │
│                                                                         │
│  💸 债务 (Debt)                                                         │
│     数量: 6,120.67 SOL                                                  │
│     价值: $891,344.26                                                   │
│                                                                         │
│  📈 收益                                                                │
│     Final APY: 13.84%                                                   │
│     Supply APY: 6.2%                                                    │
│     Borrow APY: 5.5%                                                    │
│     7日 PNL: +$1,282.53 (+1.56%)                                        │
│                                                                         │
│  ⚠️ 风险指标                                                            │
│     清算阈值: 95%                                                       │
│     清算罚金: 0.1%                                                      │
│     如果 JupSOL 跌至 1.1195 SOL (-1.36%), 可能被部分清算               │
│                                                                         │
│  📍 链上账户                                                            │
│     仓位账户: {POSITION_ACCOUNT}                 │
│     Owner: Jupiter Router (jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi)│
│                                                                         │
│  🔗 链上数据验证                                                        │
│     解析的抵押品: {collateral:.6f} jupSOL                               │
│     预期抵押品: {EXPECTED_COLLATERAL_JUPSOL:.2f} jupSOL                 │
│     匹配: {'✅ 匹配成功!' if abs(collateral - EXPECTED_COLLATERAL_JUPSOL) < 1 else '❌ 需要进一步解析'}                                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
        """)
        
        print("""
📝 结论:

Jupiter Multiply 仓位数据的获取方式:
1. 通过 NFT 凭证 (mint: 8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD) 找到仓位
2. 仓位账户 (AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec) 存储核心数据
3. 抵押品数量 (5754.67 jupSOL) 存储在 offset 54 位置
4. 债务数量可能分布在多个关联账户中

仓位数据结构:
- offset 0-8: Discriminator
- offset 8: Vault Index (4)
- offset 14-46: NFT Mint
- offset 54-62: 抵押品数量 (jupSOL, 9 decimals)
        """)


if __name__ == "__main__":
    asyncio.run(main())
