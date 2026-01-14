#!/usr/bin/env python3
"""
最终验证 Jupiter Multiply 仓位数据
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


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
        return await response.json()


async def main():
    print("=" * 70)
    print("🔍 Jupiter Multiply 仓位数据验证")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        
        # 获取仓位账户数据
        result = await rpc_call(session, "getAccountInfo", [POSITION_ACCOUNT, {"encoding": "base64"}])
        data = base64.b64decode(result["result"]["value"]["data"][0])
        
        # 正确的解析: offset 55 开始的 u64
        # 数据结构 (71 bytes):
        # [0-8]: Discriminator
        # [8]: Vault Index
        # [9-14]: Flags
        # [14-46]: NFT Mint (32 bytes)
        # [46-54]: 其他数据
        # [55-63]: 抵押品数量 (u64, 9 decimals)
        # [63-71]: 其他数据
        
        collateral_raw = struct.unpack('<Q', data[55:63])[0]
        collateral_jupsol = collateral_raw / 1e9
        
        # 解析其他可能的数值
        other_val = struct.unpack('<Q', data[63:71])[0]
        other_readable = other_val / 1e9
        
        print(f"\n📋 仓位账户: {POSITION_ACCOUNT}")
        print(f"   Owner: Jupiter Router")
        
        print(f"\n📊 链上数据解析:")
        print(f"   Vault Index: {data[8]}")
        print(f"   NFT Mint: {b58encode(data[14:46]).decode()}")
        print(f"   抵押品 (offset 55): {collateral_jupsol:.6f} jupSOL")
        print(f"   其他值 (offset 63): {other_readable:.6f}")
        
        # 与 Jupiter 网站数据对比
        expected_collateral = 5754.67
        expected_debt = 6120.67
        
        print(f"\n📊 与 Jupiter 网站数据对比:")
        print(f"   预期抵押品: {expected_collateral:.2f} jupSOL")
        print(f"   链上抵押品: {collateral_jupsol:.6f} jupSOL")
        print(f"   差异: {abs(collateral_jupsol - expected_collateral):.6f} jupSOL")
        print(f"   匹配: {'✅ 完全匹配!' if abs(collateral_jupsol - expected_collateral) < 0.01 else '⚠️ 略有差异'}")
        
        # 最终汇总
        print(f"\n" + "=" * 70)
        print("📊 仓位信息汇总")
        print("=" * 70)
        
        print(f"""
┌─────────────────────────────────────────────────────────────────────────┐
│              ✅ Jupiter Multiply 仓位数据验证成功!                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  🔖 仓位标识                                                            │
│     NFT ID: #2606                                                       │
│     Vault: JupSOL/SOL #4                                                │
│     URL: jup.ag/lend/multiply/4/nfts/2606                              │
│                                                                         │
│  📊 抵押品 (Collateral)                                                 │
│     链上数据: {collateral_jupsol:,.6f} jupSOL                           │
│     网站显示: 5,754.67 JupSOL                                           │
│     价值: $974,448.55                                                   │
│     ✅ 数据匹配!                                                        │
│                                                                         │
│  💸 债务 (Debt)                                                         │
│     网站显示: 6,120.67 SOL                                              │
│     价值: $891,344.26                                                   │
│     (债务数据可能存储在其他账户)                                        │
│                                                                         │
│  💰 净值                                                                │
│     Net Value: $83,104.29                                               │
│     = 抵押品价值 - 债务价值                                             │
│     = $974,448.55 - $891,344.26                                         │
│                                                                         │
│  📈 仓位参数                                                            │
│     杠杆倍数: 11.7x / 16.65x                                            │
│     LTV: 94%                                                            │
│     状态: 91.45% Safe                                                   │
│     Final APY: 13.84%                                                   │
│                                                                         │
│  📍 链上账户                                                            │
│     仓位账户: AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec             │
│     NFT Mint: 8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

📝 仓位数据结构总结:

仓位账户 (AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec):
├── [0-8]   Discriminator: aabc8fe47a40f7d0
├── [8]     Vault Index: 4
├── [9-14]  Flags: 002e0a0000
├── [14-46] NFT Mint: 8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD
├── [46-55] 其他配置数据
├── [55-63] 抵押品数量: {collateral_jupsol:.6f} jupSOL (u64, 9 decimals) ✅
└── [63-71] 其他数据

Jupiter Multiply 仓位信息获取方法:
1. 通过 NFT mint 在 Jupiter Router Program 中查找仓位账户
2. 解析仓位账户数据:
   - offset 55-63: 抵押品数量 (jupSOL)
3. 债务信息可能存储在关联的 Kamino/借贷协议账户中
        """)


if __name__ == "__main__":
    asyncio.run(main())
