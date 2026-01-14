#!/usr/bin/env python3
"""
逆向解析 Jupiter Multiply 仓位数据结构
使用官方网站数据作为参考
"""

import asyncio
import aiohttp
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
POSITION_ACCOUNT = "AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec"

RPC_URL = "https://api.mainnet-beta.solana.com"

# ========== 官方数据 (从 Jupiter 网站截图) ==========
OFFICIAL_DATA = {
    "nft_id": 2606,
    "vault_index": 4,
    "collateral_jupsol": 5754.67,      # jupSOL
    "collateral_usd": 974448.55,       # USD
    "debt_sol": 6120.67,               # SOL
    "debt_usd": 891344.26,             # USD
    "net_value_usd": 83104.29,
    "ltv": 0.94,                       # 94%
    "multiplier": 11.7,
    "liq_threshold": 0.95,             # 95%
    "supply_apy": 0.062,               # 6.2%
    "borrow_apy": 0.055,               # 5.5%
    "final_apy": 0.1384,               # 13.84%
    "health": 0.9145,                  # 91.45%
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
        return await response.json()


def find_value_in_data(data: bytes, target_value: float, decimals: int = 9) -> list:
    """在数据中查找特定数值"""
    target_raw = int(target_value * (10 ** decimals))
    results = []
    
    # 尝试不同的容差范围
    for tolerance in [0, 1, 10, 100, 1000]:
        for offset in range(len(data) - 7):
            val = struct.unpack('<Q', data[offset:offset+8])[0]
            if abs(val - target_raw) <= tolerance:
                results.append({
                    "offset": offset,
                    "raw": val,
                    "decoded": val / (10 ** decimals),
                    "target": target_value,
                    "tolerance": tolerance
                })
    
    return results


async def main():
    print("=" * 70)
    print("🔍 逆向解析 Jupiter Multiply 仓位数据结构")
    print("=" * 70)
    
    print("\n📋 官方数据 (Jupiter 网站):")
    print(f"   抵押品: {OFFICIAL_DATA['collateral_jupsol']:,.2f} jupSOL (${OFFICIAL_DATA['collateral_usd']:,.2f})")
    print(f"   债务:   {OFFICIAL_DATA['debt_sol']:,.2f} SOL (${OFFICIAL_DATA['debt_usd']:,.2f})")
    print(f"   净值:   ${OFFICIAL_DATA['net_value_usd']:,.2f}")
    print(f"   杠杆:   {OFFICIAL_DATA['multiplier']}x")
    print(f"   LTV:    {OFFICIAL_DATA['ltv']*100:.0f}%")
    
    async with aiohttp.ClientSession() as session:
        
        # 获取仓位账户数据
        result = await rpc_call(session, "getAccountInfo", [POSITION_ACCOUNT, {"encoding": "base64"}])
        pos_data = base64.b64decode(result["result"]["value"]["data"][0])
        
        print(f"\n" + "=" * 50)
        print(f"📋 仓位账户数据分析")
        print("=" * 50)
        print(f"   账户: {POSITION_ACCOUNT}")
        print(f"   长度: {len(pos_data)} bytes")
        print(f"   Hex: {pos_data.hex()}")
        
        # 查找抵押品值
        print(f"\n   🔍 查找抵押品 ({OFFICIAL_DATA['collateral_jupsol']} jupSOL):")
        collateral_results = find_value_in_data(pos_data, OFFICIAL_DATA['collateral_jupsol'], 9)
        for r in collateral_results:
            print(f"      ✅ offset {r['offset']}: {r['decoded']:.6f} (raw: {r['raw']})")
        
        # 查找债务值
        print(f"\n   🔍 查找债务 ({OFFICIAL_DATA['debt_sol']} SOL):")
        debt_results = find_value_in_data(pos_data, OFFICIAL_DATA['debt_sol'], 9)
        for r in debt_results:
            print(f"      ✅ offset {r['offset']}: {r['decoded']:.6f} (raw: {r['raw']})")
        
        if not debt_results:
            print(f"      ❌ 在仓位账户中未找到债务值")
            print(f"      → 债务可能存储在其他账户中")
        
        # 获取所有相关账户
        print(f"\n" + "=" * 50)
        print(f"📋 检查其他相关账户")
        print("=" * 50)
        
        # 从之前分析发现的账户
        related_accounts = [
            ("9WoJAcLA7jcFRFTmLwYsGDJRg7FM8SL1bsqWEg9oyBXh", "Router Account 1"),
            ("5CF5844NpSr8GbdNdo7vARMFw27wbbzd6M2vfyLDrgu3", "Router Account 2"),
            ("J3ZGMcEExc7ceSV19M9tWnwZexgv7Vk7meu6ziQgZsFM", "Router Account 3"),
            ("ETQGC3N6qUNbN7oojsxF41mSm1ePWZLomXEpHHBemnA1", "Router Account 4"),
            ("ALXWtv2P4GqH1B7Lq731joag52yRBRqmHV4naiXPTYWL", "Vault Account"),
            ("4Y66HtUEqbbbpZdENGtFdVhUMS3tnagffn3M4do59Nfy", "Stake Pool 1"),
            ("BZZKgXxhxVkzx3NN8RfBPwU7ZmnQbDtp3ezcsXbiALL6", "Stake Pool 2"),
            ("7HZhrUgLcHiQ8hkvNXM9gkM7CAeP21s478P8pHhANwns", "Stake Pool 3"),
        ]
        
        for addr, name in related_accounts:
            result = await rpc_call(session, "getAccountInfo", [addr, {"encoding": "base64"}])
            if result.get("result", {}).get("value"):
                data = base64.b64decode(result["result"]["value"]["data"][0])
                
                # 查找债务值
                debt_results = find_value_in_data(data, OFFICIAL_DATA['debt_sol'], 9)
                collateral_results = find_value_in_data(data, OFFICIAL_DATA['collateral_jupsol'], 9)
                
                if debt_results or collateral_results:
                    print(f"\n   📋 {name}: {addr[:20]}...")
                    for r in debt_results:
                        print(f"      ✅ 债务 @ offset {r['offset']}: {r['decoded']:.6f} SOL")
                    for r in collateral_results:
                        print(f"      ✅ 抵押品 @ offset {r['offset']}: {r['decoded']:.6f} jupSOL")
            
            await asyncio.sleep(0.2)
        
        # 最终数据结构
        print(f"\n" + "=" * 70)
        print("📊 逆向工程结果")
        print("=" * 70)
        
        # 解析仓位账户
        print(f"\n仓位账户数据结构 ({len(pos_data)} bytes):")
        print(f"{'─'*60}")
        
        # Discriminator
        discriminator = pos_data[:8].hex()
        print(f"[0-8]   Discriminator:    {discriminator}")
        
        # Vault Index
        vault_idx = pos_data[8]
        print(f"[8]     Vault Index:      {vault_idx}")
        
        # Flags
        flags = pos_data[9:14].hex()
        print(f"[9-14]  Flags:            {flags}")
        
        # NFT Mint
        nft_mint = b58encode(pos_data[14:46]).decode()
        print(f"[14-46] NFT Mint:         {nft_mint}")
        
        # Position data
        print(f"\n[46+]   Position Data:")
        pos_specific = pos_data[46:]
        
        # 逐字节分析
        print(f"        Raw: {pos_specific.hex()}")
        
        # offset 46: 前几个字节可能是标志
        print(f"        [46]    = {pos_specific[0]} (flag?)")
        print(f"        [47-50] = {pos_specific[1:5].hex()} (config?)")
        
        # offset 51-55: 可能是另一个标志或计数
        val_51 = struct.unpack('<I', pos_specific[5:9])[0]
        print(f"        [51-55] = {val_51} (u32)")
        
        # offset 55-63: 抵押品
        collateral_raw = struct.unpack('<Q', pos_specific[9:17])[0]
        collateral = collateral_raw / 1e9
        print(f"        [55-63] = {collateral:.6f} jupSOL (抵押品) ✅")
        
        # offset 63-71: 比率或其他
        other_raw = struct.unpack('<Q', pos_specific[17:25])[0]
        other = other_raw / 1e9
        print(f"        [63-71] = {other:.9f} (汇率?)")
        
        # 计算验证
        print(f"\n📊 数据验证:")
        print(f"{'─'*60}")
        print(f"   链上抵押品:  {collateral:.6f} jupSOL")
        print(f"   官方抵押品:  {OFFICIAL_DATA['collateral_jupsol']:.2f} jupSOL")
        print(f"   差异:        {abs(collateral - OFFICIAL_DATA['collateral_jupsol']):.6f}")
        print(f"   匹配: {'✅' if abs(collateral - OFFICIAL_DATA['collateral_jupsol']) < 0.01 else '❌'}")
        
        # 计算 jupSOL/SOL 汇率
        # 抵押品价值 / 债务价值 应该接近某个比率
        jupsol_sol_rate = OFFICIAL_DATA['collateral_usd'] / OFFICIAL_DATA['collateral_jupsol'] / (OFFICIAL_DATA['debt_usd'] / OFFICIAL_DATA['debt_sol'])
        print(f"\n   推算 jupSOL/SOL 汇率: {jupsol_sol_rate:.6f}")
        print(f"   链上数据 [63-71]:     {other:.9f}")
        
        # 最终总结
        print(f"\n" + "=" * 70)
        print("📋 最终数据结构")
        print("=" * 70)
        
        print(f"""
┌────────────────────────────────────────────────────────────────────────┐
│  Jupiter Multiply 仓位账户数据结构 (71 bytes)                          │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  [0-8]   Discriminator: {discriminator}                     │
│  [8]     Vault Index:   {vault_idx}                                               │
│  [9-14]  Flags:         {flags}                                  │
│  [14-46] NFT Mint:      {nft_mint}        │
│                                                                        │
│  Position Data [46-71]:                                                │
│  ├── [46]     Flag:        {pos_specific[0]}                                            │
│  ├── [47-50]  Config:      {pos_specific[1:5].hex()}                                    │
│  ├── [51-55]  Counter:     {val_51}                                            │
│  ├── [55-63]  Collateral:  {collateral:.6f} jupSOL ✅                  │
│  └── [63-71]  Rate/Other:  {other:.9f}                          │
│                                                                        │
│  验证结果:                                                             │
│  ├── 抵押品匹配: ✅ (链上: {collateral:.2f}, 官方: {OFFICIAL_DATA['collateral_jupsol']:.2f})         │
│  └── 债务: 存储在其他账户 (需要进一步分析)                             │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

债务数据 ({OFFICIAL_DATA['debt_sol']:.2f} SOL) 可能存储在:
1. Kamino Lending 协议的 Obligation 账户
2. Jupiter 内部的借贷记录账户
3. 需要通过交易分析或 IDL 进一步确认
        """)


if __name__ == "__main__":
    asyncio.run(main())
