#!/usr/bin/env python3
"""
显示 Jupiter Multiply 仓位的具体数据
"""

import asyncio
import aiohttp
import json
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"
NFT_TOKEN_ACCOUNT = "CVxBujMbbNszmGygDbi12Dy8NCAjw5dYNeX3z6NmhjKS"

RPC_URL = "https://api.mainnet-beta.solana.com"

# 从之前分析发现的关键账户
POSITION_ACCOUNT = "AWCKkAgmh8B2ERrTFwTP1UGfpK7XPXc46Q4tiaiS3oec"

# Jupiter Stake Pool 相关账户 (包含 jupSOL 数据)
JUPSOL_ACCOUNTS = [
    "7HZhrUgLcHiQ8hkvNXM9gkM7CAeP21s478P8pHhANwns",
    "9DiqWS3ooZHprymNuwxQ4PcjXHRBPjtAvvWEtrpSoaxT",
]

# wSOL 相关账户
WSOL_ACCOUNTS = [
    "4Y66HtUEqbbbpZdENGtFdVhUMS3tnagffn3M4do59Nfy",
    "BZZKgXxhxVkzx3NN8RfBPwU7ZmnQbDtp3ezcsXbiALL6",
]

# Vault 账户
VAULT_ACCOUNT = "ALXWtv2P4GqH1B7Lq731joag52yRBRqmHV4naiXPTYWL"

# Router 账户
ROUTER_ACCOUNTS = [
    "5CF5844NpSr8GbdNdo7vARMFw27wbbzd6M2vfyLDrgu3",
    "J3ZGMcEExc7ceSV19M9tWnwZexgv7Vk7meu6ziQgZsFM", 
    "9WoJAcLA7jcFRFTmLwYsGDJRg7FM8SL1bsqWEg9oyBXh",
    "ETQGC3N6qUNbN7oojsxF41mSm1ePWZLomXEpHHBemnA1",
]


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def get_account_data(session: aiohttp.ClientSession, address: str) -> bytes:
    """获取账户数据"""
    result = await rpc_call(session, "getAccountInfo", [address, {"encoding": "base64"}])
    value = result.get("result", {}).get("value")
    if value and value.get("data"):
        return base64.b64decode(value["data"][0])
    return b""


async def get_token_balance(session: aiohttp.ClientSession, owner: str, mint: str) -> float:
    """获取代币余额"""
    result = await rpc_call(session, "getTokenAccountsByOwner", [
        owner,
        {"mint": mint},
        {"encoding": "jsonParsed"}
    ])
    
    accounts = result.get("result", {}).get("value", [])
    if accounts:
        return float(accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
    return 0.0


async def fetch_uri_metadata(session: aiohttp.ClientSession, uri: str) -> dict:
    """获取 URI 元数据"""
    try:
        async with session.get(uri, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                return await response.json()
    except:
        pass
    return {}


async def main():
    print("=" * 70)
    print("🔍 Jupiter Multiply 仓位详情")
    print("=" * 70)
    print(f"\n📍 钱包地址: {TARGET_ADDRESS}")
    print(f"📍 NFT Mint: {NFT_MINT}")
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 获取 NFT 元数据
        print("\n" + "=" * 50)
        print("📋 1. NFT 仓位凭证信息")
        print("=" * 50)
        
        uri = "https://cdn.instadapp.io/solana/vaults/metadata/4.json"
        metadata = await fetch_uri_metadata(session, uri)
        
        print(f"\n   名称: {metadata.get('name', 'N/A')}")
        print(f"   符号: {metadata.get('symbol', 'N/A')}")
        print(f"   描述: {metadata.get('description', 'N/A')}")
        print(f"   图片: {metadata.get('image', 'N/A')}")
        
        # 2. 获取用户的代币余额
        print("\n" + "=" * 50)
        print("📋 2. 用户钱包余额")
        print("=" * 50)
        
        # SOL
        sol_result = await rpc_call(session, "getBalance", [TARGET_ADDRESS])
        sol_balance = sol_result.get("result", {}).get("value", 0) / 1e9
        print(f"\n   SOL: {sol_balance:.6f}")
        
        # jupSOL
        jupsol_balance = await get_token_balance(session, TARGET_ADDRESS, "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v")
        print(f"   jupSOL: {jupsol_balance:.6f}")
        
        # JitoSOL
        jitosol_balance = await get_token_balance(session, TARGET_ADDRESS, "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn")
        print(f"   JitoSOL: {jitosol_balance:.6f}")
        
        # 3. 解析仓位账户
        print("\n" + "=" * 50)
        print("📋 3. 仓位账户数据")
        print("=" * 50)
        
        # 仓位凭证账户
        print(f"\n   🔹 仓位凭证账户: {POSITION_ACCOUNT}")
        pos_data = await get_account_data(session, POSITION_ACCOUNT)
        if pos_data:
            print(f"      数据长度: {len(pos_data)} bytes")
            print(f"      Discriminator: {pos_data[:8].hex()}")
            
            # 解析仓位数据
            # 根据之前的分析，数据结构大概是:
            # offset 0-8: discriminator
            # offset 8-14: 其他数据
            # offset 14-46: NFT mint (32 bytes)
            # offset 46-: 其他仓位数据
            
            if len(pos_data) >= 71:
                # 尝试解析一些数值
                print(f"\n      原始数据解析:")
                
                # 解析可能的数量字段
                for offset in [46, 54, 62]:
                    if offset + 8 <= len(pos_data):
                        value = struct.unpack('<Q', pos_data[offset:offset+8])[0]
                        if value > 0:
                            print(f"      offset {offset}: {value} ({value/1e9:.6f} 如果是9位小数)")
        
        # 4. 分析 Vault 账户
        print(f"\n   🔹 Vault 账户: {VAULT_ACCOUNT}")
        vault_data = await get_account_data(session, VAULT_ACCOUNT)
        if vault_data:
            print(f"      数据长度: {len(vault_data)} bytes")
            
            # 解析数值
            amounts = []
            for offset in range(8, min(len(vault_data) - 8, 200), 8):
                value = struct.unpack('<Q', vault_data[offset:offset+8])[0]
                if 1_000_000 < value < 10_000_000_000_000_000:
                    amounts.append((offset, value, value / 1e9))
            
            if amounts:
                print(f"\n      发现的数量值:")
                for offset, raw, readable in amounts[:5]:
                    print(f"      offset {offset}: {readable:.6f}")
        
        # 5. 分析 Router 账户
        print(f"\n   🔹 Router 账户分析:")
        
        for acc in ROUTER_ACCOUNTS:
            data = await get_account_data(session, acc)
            if data:
                amounts = []
                for offset in range(8, min(len(data) - 8, 200), 8):
                    try:
                        value = struct.unpack('<Q', data[offset:offset+8])[0]
                        if 100_000_000 < value < 10_000_000_000_000_000:  # 0.1 到 10M
                            amounts.append((offset, value / 1e9))
                    except:
                        pass
                
                if amounts:
                    print(f"\n      {acc[:20]}...")
                    for offset, readable in amounts[:3]:
                        print(f"         offset {offset}: {readable:.6f}")
        
        # 6. 获取最近交易中的仓位变化
        print("\n" + "=" * 50)
        print("📋 4. 最近仓位变化 (从交易记录)")
        print("=" * 50)
        
        result = await rpc_call(session, "getSignaturesForAddress", [
            NFT_TOKEN_ACCOUNT,
            {"limit": 3}
        ])
        
        signatures = result.get("result", [])
        
        for sig_info in signatures[:2]:
            sig = sig_info["signature"]
            print(f"\n   交易: {sig[:40]}...")
            
            tx_result = await rpc_call(session, "getTransaction", [
                sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ])
            
            tx = tx_result.get("result")
            if tx:
                meta = tx.get("meta", {})
                
                # 代币变化
                pre_balances = meta.get("preTokenBalances", [])
                post_balances = meta.get("postTokenBalances", [])
                
                changes = {}
                for post in post_balances:
                    mint = post.get("mint")
                    owner = post.get("owner")
                    post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount") or 0)
                    
                    pre_amount = 0
                    for pre in pre_balances:
                        if pre.get("accountIndex") == post.get("accountIndex"):
                            pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount") or 0)
                            break
                    
                    change = post_amount - pre_amount
                    if abs(change) > 0.0001:
                        if mint == "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v":
                            token = "jupSOL"
                        elif mint == "So11111111111111111111111111111111111111112":
                            token = "wSOL"
                        else:
                            token = mint[:12] + "..."
                        
                        key = f"{token}|{owner[:16] if owner else 'unknown'}"
                        if key not in changes:
                            changes[key] = {"token": token, "owner": owner, "change": 0}
                        changes[key]["change"] += change
                
                if changes:
                    print(f"   代币变化:")
                    for key, info in changes.items():
                        symbol = "+" if info["change"] > 0 else ""
                        is_user = info["owner"] == TARGET_ADDRESS if info["owner"] else False
                        user_marker = " (用户)" if is_user else ""
                        print(f"      {info['token']}: {symbol}{info['change']:.6f}{user_marker}")
            
            await asyncio.sleep(0.5)
        
        # 7. 汇总
        print("\n" + "=" * 70)
        print("📊 仓位汇总")
        print("=" * 70)
        
        print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│  Jupiter Multiply 仓位                                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  📋 仓位类型: jupSOL/SOL 杠杆仓位 (Vault #4)                        │
│                                                                     │
│  🏦 NFT 凭证:                                                       │
│     Mint: {NFT_MINT}              │
│     名称: Jupiter JUPSOL/SOL 4                                      │
│                                                                     │
│  💰 钱包余额:                                                       │
│     SOL: {sol_balance:.6f}                                          │
│     jupSOL: {jupsol_balance:.6f}                                    │
│                                                                     │
│  📍 关键账户:                                                       │
│     仓位账户: {POSITION_ACCOUNT}  │
│     Vault账户: {VAULT_ACCOUNT}    │
│                                                                     │
│  ⚙️ 相关 Programs:                                                  │
│     Jupiter Vault: jupgfSgfuAXv4B6R2Uxu85Z1qdzgju79s6MfZekN6XS     │
│     Jupiter Router: jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

注意: 仓位的具体抵押品和借款数量需要根据 Jupiter Multiply 的
      账户数据结构进一步解析。目前显示的是从链上账户中发现的原始数据。
        """)


if __name__ == "__main__":
    asyncio.run(main())
