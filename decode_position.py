#!/usr/bin/env python3
"""
精确解析 Jupiter Multiply 仓位数据
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

# 关键账户
POSITION_ACCOUNT = "AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec"
ROUTER_ACCOUNT = "9WoJAcLA7jcFRFTmLwYsGDJRg7FM8SL1bsqWEg9oyBXh"


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def get_account_data(session: aiohttp.ClientSession, address: str) -> tuple:
    """获取账户数据和 owner"""
    result = await rpc_call(session, "getAccountInfo", [address, {"encoding": "base64"}])
    value = result.get("result", {}).get("value")
    if value and value.get("data"):
        return base64.b64decode(value["data"][0]), value.get("owner")
    return b"", None


def decode_position_data(data: bytes):
    """解码仓位数据"""
    print(f"\n   数据长度: {len(data)} bytes")
    print(f"   完整 hex: {data.hex()}")
    
    # Discriminator (8 bytes)
    discriminator = data[:8].hex()
    print(f"\n   Discriminator: {discriminator}")
    
    # 接下来的数据
    offset = 8
    
    # 可能是一些标志位或索引
    if len(data) >= 14:
        flags = data[8:14]
        print(f"   Flags (offset 8-14): {flags.hex()}")
        offset = 14
    
    # NFT Mint (32 bytes at offset 14)
    if len(data) >= 46:
        nft_mint_bytes = data[14:46]
        try:
            nft_mint = b58encode(nft_mint_bytes).decode()
            print(f"   NFT Mint (offset 14-46): {nft_mint}")
        except:
            print(f"   NFT Mint bytes: {nft_mint_bytes.hex()}")
        offset = 46
    
    # 剩余数据
    if len(data) > 46:
        remaining = data[46:]
        print(f"\n   剩余数据 (offset 46+): {remaining.hex()}")
        
        # 尝试解析为各种格式
        print(f"\n   尝试解析剩余数据:")
        
        # u8 序列
        print(f"   as u8: {list(remaining[:10])}")
        
        # u16
        for i in range(0, min(len(remaining)-1, 10), 2):
            val = struct.unpack('<H', remaining[i:i+2])[0]
            print(f"   u16 at {46+i}: {val}")
        
        # u32
        for i in range(0, min(len(remaining)-3, 16), 4):
            val = struct.unpack('<I', remaining[i:i+4])[0]
            print(f"   u32 at {46+i}: {val}")
        
        # u64
        for i in range(0, min(len(remaining)-7, 24), 8):
            val = struct.unpack('<Q', remaining[i:i+8])[0]
            if val > 0:
                print(f"   u64 at {46+i}: {val} ({val/1e9:.9f} as 9 decimals)")


def decode_router_data(data: bytes):
    """解码 Router 账户数据"""
    print(f"\n   数据长度: {len(data)} bytes")
    print(f"   Discriminator: {data[:8].hex()}")
    
    # 尝试找到有意义的数值
    print(f"\n   解析 u64 数值:")
    for offset in range(8, len(data) - 7, 8):
        val = struct.unpack('<Q', data[offset:offset+8])[0]
        if val > 0:
            readable = val / 1e9
            if 0.001 < readable < 100000000:  # 合理的代币范围
                print(f"   offset {offset}: {readable:.9f}")


async def main():
    print("=" * 70)
    print("🔍 精确解析 Jupiter Multiply 仓位数据")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 解析仓位凭证账户
        print(f"\n{'='*50}")
        print(f"📋 仓位凭证账户: {POSITION_ACCOUNT}")
        print("=" * 50)
        
        data, owner = await get_account_data(session, POSITION_ACCOUNT)
        if data:
            print(f"   Owner Program: {owner}")
            decode_position_data(data)
        
        # 2. 解析 Router 账户
        print(f"\n{'='*50}")
        print(f"📋 Router 账户: {ROUTER_ACCOUNT}")
        print("=" * 50)
        
        data, owner = await get_account_data(session, ROUTER_ACCOUNT)
        if data:
            print(f"   Owner Program: {owner}")
            decode_router_data(data)
        
        # 3. 获取用户在各个代币的余额变化 (通过最近交易)
        print(f"\n{'='*50}")
        print("📋 从最近交易推算仓位")
        print("=" * 50)
        
        # 获取 NFT token account 的交易
        result = await rpc_call(session, "getSignaturesForAddress", [
            "CVxBujMbbNszmGygDbi12Dy8NCAjw5dYNeX3z6NmhjKS",
            {"limit": 5}
        ])
        
        signatures = result.get("result", [])
        
        total_jupsol_change = 0
        total_sol_change = 0
        
        for sig_info in signatures:
            sig = sig_info["signature"]
            
            tx_result = await rpc_call(session, "getTransaction", [
                sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ])
            
            tx = tx_result.get("result")
            if tx:
                meta = tx.get("meta", {})
                pre_balances = meta.get("preTokenBalances", [])
                post_balances = meta.get("postTokenBalances", [])
                
                # 只看用户的代币变化
                for post in post_balances:
                    if post.get("owner") == TARGET_ADDRESS:
                        mint = post.get("mint")
                        post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount") or 0)
                        
                        pre_amount = 0
                        for pre in pre_balances:
                            if pre.get("accountIndex") == post.get("accountIndex"):
                                pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount") or 0)
                                break
                        
                        change = post_amount - pre_amount
                        
                        if mint == "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v":
                            total_jupsol_change += change
                        elif mint == "So11111111111111111111111111111111111111112":
                            total_sol_change += change
        
        print(f"\n   用户在最近交易中的净变化:")
        print(f"   jupSOL: {total_jupsol_change:+.6f}")
        print(f"   SOL: {total_sol_change:+.6f}")
        
        # 4. 当前余额
        print(f"\n{'='*50}")
        print("📋 当前钱包余额")
        print("=" * 50)
        
        # SOL
        sol_result = await rpc_call(session, "getBalance", [TARGET_ADDRESS])
        sol_balance = sol_result.get("result", {}).get("value", 0) / 1e9
        
        # jupSOL
        result = await rpc_call(session, "getTokenAccountsByOwner", [
            TARGET_ADDRESS,
            {"mint": "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v"},
            {"encoding": "jsonParsed"}
        ])
        jupsol_balance = 0
        accounts = result.get("result", {}).get("value", [])
        if accounts:
            jupsol_balance = float(accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
        
        print(f"\n   SOL: {sol_balance:.6f}")
        print(f"   jupSOL: {jupsol_balance:.6f}")
        
        # 5. 汇总
        print(f"\n{'='*70}")
        print("📊 仓位信息汇总")
        print("=" * 70)
        
        print(f"""
┌────────────────────────────────────────────────────────────────────────┐
│  Jupiter Multiply 仓位 (jupSOL/SOL Vault #4)                          │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  🏦 NFT 凭证:                                                          │
│     Mint: {NFT_MINT}                │
│     名称: Jupiter JUPSOL/SOL 4                                         │
│                                                                        │
│  💼 仓位账户:                                                          │
│     地址: {POSITION_ACCOUNT}                │
│     Owner: jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi                │
│                                                                        │
│  💰 当前钱包余额:                                                      │
│     SOL: {sol_balance:.6f}                                               │
│     jupSOL: {jupsol_balance:.6f}                                         │
│                                                                        │
│  📊 仓位机制:                                                          │
│     - 用户存入 jupSOL 作为抵押品                                       │
│     - 借入 SOL                                                         │
│     - 将借入的 SOL 兑换为 jupSOL                                       │
│     - 重复以上步骤实现杠杆                                             │
│                                                                        │
│  ⚠️ 注意:                                                              │
│     具体的抵押品数量、借款数量、杠杆倍数等详细信息                     │
│     需要完整解析 Jupiter Multiply 的 IDL 才能准确显示                  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
        """)


if __name__ == "__main__":
    asyncio.run(main())
