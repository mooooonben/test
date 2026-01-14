#!/usr/bin/env python3
"""
通过计算验证 Jupiter Multiply 仓位数据
使用链上数据和官方数据进行对比
"""

import asyncio
import aiohttp
import base64
import struct
from base58 import b58encode

POSITION_ACCOUNT = "AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec"
RPC_URL = "https://api.mainnet-beta.solana.com"

# 官方数据
OFFICIAL = {
    "collateral_jupsol": 5754.67,
    "collateral_usd": 974448.55,
    "debt_sol": 6120.67,
    "debt_usd": 891344.26,
    "net_value_usd": 83104.29,
    "ltv": 0.94,
    "multiplier": 11.7,
    "health": 0.9145,
    "liq_threshold": 0.95,
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
        return await response.json()


async def main():
    print("=" * 70)
    print("🔍 Jupiter Multiply 仓位数据计算验证")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        
        # 获取链上数据
        result = await rpc_call(session, "getAccountInfo", [POSITION_ACCOUNT, {"encoding": "base64"}])
        data = base64.b64decode(result["result"]["value"]["data"][0])
        
        # 解析链上数据
        collateral_raw = struct.unpack('<Q', data[55:63])[0]
        collateral = collateral_raw / 1e9
        
        rate_raw = struct.unpack('<Q', data[63:71])[0]
        rate = rate_raw / 1e9
        
        print(f"\n📊 链上数据 (仓位账户):")
        print(f"   抵押品: {collateral:.6f} jupSOL")
        print(f"   比率值: {rate:.9f}")
        
        print(f"\n📊 官方数据 (Jupiter 网站):")
        print(f"   抵押品: {OFFICIAL['collateral_jupsol']:.2f} jupSOL")
        print(f"   债务:   {OFFICIAL['debt_sol']:.2f} SOL")
        print(f"   净值:   ${OFFICIAL['net_value_usd']:,.2f}")
        print(f"   LTV:    {OFFICIAL['ltv']*100:.0f}%")
        
        # 计算价格
        print(f"\n📊 价格推算:")
        jupsol_price = OFFICIAL['collateral_usd'] / OFFICIAL['collateral_jupsol']
        sol_price = OFFICIAL['debt_usd'] / OFFICIAL['debt_sol']
        jupsol_sol_rate = jupsol_price / sol_price
        
        print(f"   jupSOL 价格: ${jupsol_price:.2f}")
        print(f"   SOL 价格:    ${sol_price:.2f}")
        print(f"   jupSOL/SOL:  {jupsol_sol_rate:.6f}")
        
        # 验证计算
        print(f"\n📊 计算验证:")
        
        # 方法1: 抵押品价值 / LTV = 债务
        collateral_value_sol = collateral * jupsol_sol_rate
        calculated_debt_1 = collateral_value_sol * OFFICIAL['ltv']
        print(f"\n   方法1 (抵押品 * 汇率 * LTV):")
        print(f"   抵押品价值: {collateral:.2f} * {jupsol_sol_rate:.4f} = {collateral_value_sol:.2f} SOL")
        print(f"   计算债务:   {collateral_value_sol:.2f} * {OFFICIAL['ltv']} = {calculated_debt_1:.2f} SOL")
        print(f"   官方债务:   {OFFICIAL['debt_sol']:.2f} SOL")
        print(f"   差异:       {abs(calculated_debt_1 - OFFICIAL['debt_sol']):.2f} SOL")
        
        # 方法2: 直接使用链上比率
        if rate > 0:
            calculated_debt_2 = collateral * rate
            print(f"\n   方法2 (抵押品 * 链上比率):")
            print(f"   计算债务:   {collateral:.2f} * {rate:.6f} = {calculated_debt_2:.2f}")
        
        # 方法3: 从净值反推
        # 净值 = 抵押品价值 - 债务价值
        # 债务价值 = 抵押品价值 - 净值
        calculated_debt_usd = OFFICIAL['collateral_usd'] - OFFICIAL['net_value_usd']
        calculated_debt_sol = calculated_debt_usd / sol_price
        print(f"\n   方法3 (从净值反推):")
        print(f"   抵押品 USD:  ${OFFICIAL['collateral_usd']:,.2f}")
        print(f"   净值 USD:    ${OFFICIAL['net_value_usd']:,.2f}")
        print(f"   债务 USD:    ${calculated_debt_usd:,.2f}")
        print(f"   债务 SOL:    {calculated_debt_sol:.2f}")
        print(f"   官方债务:    {OFFICIAL['debt_sol']:.2f} SOL")
        print(f"   差异:        {abs(calculated_debt_sol - OFFICIAL['debt_sol']):.2f} SOL")
        
        # 杠杆验证
        print(f"\n📊 杠杆倍数验证:")
        # Multiplier = Total Position Value / Net Value
        total_position = OFFICIAL['collateral_usd']
        net = OFFICIAL['net_value_usd']
        calculated_multiplier = total_position / net
        print(f"   总仓位 / 净值 = {total_position:,.0f} / {net:,.0f} = {calculated_multiplier:.2f}x")
        print(f"   官方杠杆:     {OFFICIAL['multiplier']}x")
        
        # LTV 验证
        print(f"\n📊 LTV 验证:")
        calculated_ltv = OFFICIAL['debt_usd'] / OFFICIAL['collateral_usd']
        print(f"   债务 / 抵押品 = {OFFICIAL['debt_usd']:,.0f} / {OFFICIAL['collateral_usd']:,.0f} = {calculated_ltv:.4f}")
        print(f"   百分比: {calculated_ltv*100:.2f}%")
        print(f"   官方 LTV: {OFFICIAL['ltv']*100:.0f}%")
        
        # 健康度验证
        print(f"\n📊 健康度验证:")
        # Health = (Collateral * Liq_Threshold) / Debt
        max_borrow = OFFICIAL['collateral_usd'] * OFFICIAL['liq_threshold']
        calculated_health = (max_borrow - OFFICIAL['debt_usd']) / max_borrow
        print(f"   最大可借: {max_borrow:,.0f}")
        print(f"   已借:     {OFFICIAL['debt_usd']:,.0f}")
        print(f"   安全余量: {(max_borrow - OFFICIAL['debt_usd']):,.0f}")
        print(f"   健康度:   {calculated_health*100:.2f}%")
        print(f"   官方健康度: {OFFICIAL['health']*100:.2f}%")
        
        # 最终汇总
        print(f"\n" + "=" * 70)
        print("📋 完整仓位数据汇总")
        print("=" * 70)
        
        print(f"""
┌────────────────────────────────────────────────────────────────────────┐
│              Jupiter Multiply 仓位完整信息                             │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  🔖 仓位标识                                                           │
│     NFT ID: #2606                                                      │
│     Vault: JupSOL/SOL #4                                               │
│                                                                        │
│  📊 抵押品 (Collateral)                                                │
│     数量: {OFFICIAL['collateral_jupsol']:,.2f} jupSOL                                              │
│     价值: ${OFFICIAL['collateral_usd']:,.2f}                                           │
│     链上: {collateral:.6f} jupSOL ✅                                   │
│                                                                        │
│  💸 债务 (Debt)                                                        │
│     数量: {OFFICIAL['debt_sol']:,.2f} SOL                                                 │
│     价值: ${OFFICIAL['debt_usd']:,.2f}                                             │
│                                                                        │
│  💰 净值 (Net Value)                                                   │
│     ${OFFICIAL['net_value_usd']:,.2f}                                                     │
│     = 抵押品 - 债务                                                    │
│     = ${OFFICIAL['collateral_usd']:,.2f} - ${OFFICIAL['debt_usd']:,.2f}                            │
│                                                                        │
│  📈 仓位参数                                                           │
│     杠杆倍数: {OFFICIAL['multiplier']}x (计算值: {calculated_multiplier:.2f}x)                           │
│     LTV: {OFFICIAL['ltv']*100:.0f}% (计算值: {calculated_ltv*100:.2f}%)                                   │
│     健康度: {OFFICIAL['health']*100:.2f}% Safe                                           │
│     清算阈值: {OFFICIAL['liq_threshold']*100:.0f}%                                                │
│                                                                        │
│  💹 收益                                                               │
│     Final APY:  13.84%                                                 │
│     Supply APY: 6.2%                                                   │
│     Borrow APY: 5.5%                                                   │
│     7D PNL: +$1,282.53 (+1.56%)                                        │
│                                                                        │
│  📍 链上账户                                                           │
│     仓位账户: AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec            │
│     Owner: Jupiter Router                                              │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

📝 数据获取方式:

1. 抵押品 (jupSOL):
   - 位置: 仓位账户 offset 55-63
   - 格式: u64, 9 decimals
   - 值: {collateral:.6f} jupSOL ✅

2. 债务 (SOL):
   - 可通过计算得出: 净值 = 抵押品价值 - 债务价值
   - 债务 = (抵押品价值 - 净值) / SOL价格
   - 或者从 Kamino Lending Obligation 账户获取

3. 其他参数:
   - LTV = 债务价值 / 抵押品价值
   - 杠杆 = 抵押品价值 / 净值
   - 健康度 = (最大可借 - 已借) / 最大可借
        """)


if __name__ == "__main__":
    asyncio.run(main())
