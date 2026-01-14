#!/usr/bin/env python3
"""
最终仓位数据解析
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
    print("🔍 Jupiter Multiply 仓位详情")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        
        # 获取仓位账户数据
        result = await rpc_call(session, "getAccountInfo", [POSITION_ACCOUNT, {"encoding": "base64"}])
        data = base64.b64decode(result["result"]["value"]["data"][0])
        
        print(f"\n📋 仓位账户: {POSITION_ACCOUNT}")
        print(f"   数据长度: {len(data)} bytes")
        
        # 详细解析
        print(f"\n   📊 数据结构解析:")
        
        # Discriminator
        discriminator = data[:8].hex()
        print(f"   [0-8] Discriminator: {discriminator}")
        
        # Vault Index
        vault_index = data[8]
        print(f"   [8] Vault Index: {vault_index}")
        
        # 其他标志
        flags = data[9:14].hex()
        print(f"   [9-14] Flags: {flags}")
        
        # NFT Mint
        nft_mint = b58encode(data[14:46]).decode()
        print(f"   [14-46] NFT Mint: {nft_mint}")
        
        # 剩余数据解析
        remaining = data[46:]
        print(f"\n   [46+] 仓位数据:")
        print(f"   Raw hex: {remaining.hex()}")
        
        # 解析为不同格式
        # 前几个字节可能是索引/标志
        print(f"\n   Byte 46: {remaining[0]} (可能是索引)")
        print(f"   Bytes 47-50: {remaining[1:5].hex()}")
        
        # 尝试在 offset 51 开始解析 u64
        if len(remaining) >= 17:
            val1 = struct.unpack('<Q', remaining[5:13])[0]
            val2 = struct.unpack('<Q', remaining[9:17])[0]
            val3 = struct.unpack('<Q', remaining[13:21])[0] if len(remaining) >= 21 else 0
            
            print(f"\n   可能的数量值:")
            print(f"   offset 51 (u64): {val1} = {val1/1e9:.9f} (9 dec) 或 {val1/1e6:.6f} (6 dec)")
            print(f"   offset 55 (u64): {val2} = {val2/1e9:.9f} (9 dec) 或 {val2/1e6:.6f} (6 dec)")
            print(f"   offset 59 (u64): {val3} = {val3/1e9:.9f} (9 dec) 或 {val3/1e6:.6f} (6 dec)")
        
        # 获取当前余额
        print(f"\n" + "=" * 50)
        print(f"📋 当前钱包余额")
        print("=" * 50)
        
        # SOL
        sol_result = await rpc_call(session, "getBalance", [TARGET_ADDRESS])
        sol_balance = sol_result.get("result", {}).get("value", 0) / 1e9
        print(f"\n   SOL: {sol_balance:.9f}")
        
        # jupSOL
        result = await rpc_call(session, "getTokenAccountsByOwner", [
            TARGET_ADDRESS,
            {"mint": "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v"},
            {"encoding": "jsonParsed"}
        ])
        jupsol = 0
        accounts = result.get("result", {}).get("value", [])
        if accounts:
            jupsol = float(accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
        print(f"   jupSOL: {jupsol:.9f}")
        
        # 获取 NFT 元数据
        print(f"\n" + "=" * 50)
        print(f"📋 NFT 仓位凭证")
        print("=" * 50)
        
        try:
            async with session.get("https://cdn.instadapp.io/solana/vaults/metadata/4.json") as resp:
                if resp.status == 200:
                    metadata = await resp.json()
                    print(f"\n   名称: {metadata.get('name')}")
                    print(f"   符号: {metadata.get('symbol')}")
                    print(f"   描述: {metadata.get('description')}")
        except:
            pass
        
        # 最终汇总
        print(f"\n" + "=" * 70)
        print("📊 仓位信息汇总")
        print("=" * 70)
        
        print(f"""
┌────────────────────────────────────────────────────────────────────────┐
│                    Jupiter Multiply 仓位信息                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  📦 仓位类型                                                           │
│     名称: Jupiter JUPSOL/SOL 4                                         │
│     符号: jvJUPSOL/SOL                                                 │
│     Vault Index: {vault_index}                                                       │
│                                                                        │
│  🔖 NFT 凭证                                                           │
│     Mint: {NFT_MINT}                │
│     Token Account: CVxBujMbbNszmGygDbi12Dy8NCAjw5dYNeX3z6NmhjKS       │
│                                                                        │
│  📍 仓位账户                                                           │
│     地址: {POSITION_ACCOUNT}                │
│     Owner Program: Jupiter Router                                      │
│              (jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi)             │
│                                                                        │
│  💰 当前钱包余额                                                       │
│     SOL: {sol_balance:.6f}                                               │
│     jupSOL: {jupsol:.6f}                                               │
│                                                                        │
│  ⚙️ 涉及的 Programs                                                    │
│     Jupiter Vault:  jupgfSgfuAXv4B6R2Uxu85Z1qdzgju79s6MfZekN6XS       │
│     Jupiter Router: jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi       │
│     Jupiter Stake:  jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC       │
│                                                                        │
│  📝 仓位机制                                                           │
│     这是一个杠杆做多 jupSOL/SOL 的仓位:                                │
│     1. 存入 jupSOL 作为抵押品                                          │
│     2. 借入 SOL 进行杠杆操作                                           │
│     3. 当 jupSOL 相对 SOL 升值时获利                                   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

仓位账户原始数据:
Discriminator: {discriminator}
Vault Index: {vault_index}
NFT Mint: {nft_mint}
Position Data: {remaining.hex()}

说明: 具体的抵押品数量、借款数量、杠杆倍数需要 Jupiter Multiply 的 IDL
      才能完全解析。仓位数据存储在上述账户中。
        """)


if __name__ == "__main__":
    asyncio.run(main())
