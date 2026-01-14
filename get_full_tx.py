#!/usr/bin/env python3
"""
获取完整交易信息并分析所有账户
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

KNOWN_MINTS = {
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": ("jupSOL", 9),
    "So11111111111111111111111111111111111111112": ("wSOL", 9),
}


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


async def main():
    print("=" * 80)
    print(f"🔍 获取完整交易信息")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # 获取 NFT 相关交易
        result = await rpc_call(session, "getSignaturesForAddress", [
            NFT_TOKEN_ACCOUNT,
            {"limit": 5}
        ])
        
        signatures = result.get("result", [])
        if not signatures:
            print("❌ 未找到交易")
            return
        
        # 分析每笔交易
        for sig_info in signatures[:2]:  # 只分析前2笔
            sig = sig_info["signature"]
            print(f"\n{'='*60}")
            print(f"📋 交易: {sig}")
            print("=" * 60)
            
            result = await rpc_call(session, "getTransaction", [
                sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ])
            
            tx = result.get("result")
            if not tx:
                print(f"   ❌ 无法获取: {result.get('error', '')}")
                continue
            
            message = tx.get("transaction", {}).get("message", {})
            meta = tx.get("meta", {})
            
            # 获取完整账户列表
            account_keys = message.get("accountKeys", [])
            print(f"\n   共 {len(account_keys)} 个账户:")
            
            writable_accounts = []
            
            for i, acc in enumerate(account_keys):
                if isinstance(acc, dict):
                    pubkey = acc.get("pubkey")
                    writable = acc.get("writable", False)
                    signer = acc.get("signer", False)
                else:
                    pubkey = acc
                    writable = i < len(message.get("header", {}).get("numRequiredSignatures", 0))
                    signer = writable
                
                marker = ""
                if signer:
                    marker += "[S]"
                if writable:
                    marker += "[W]"
                
                print(f"   {marker:6} [{i:2d}] {pubkey}")
                
                if writable and not signer:
                    writable_accounts.append(pubkey)
            
            # 分析指令
            print(f"\n   指令:")
            instructions = message.get("instructions", [])
            for i, ix in enumerate(instructions):
                program_id = ix.get("programId")
                accounts = ix.get("accounts", [])
                print(f"   [{i}] Program: {program_id}")
                if accounts:
                    print(f"       涉及账户索引: {accounts[:10]}")
            
            # 检查可写账户
            print(f"\n   检查可写账户:")
            
            for pubkey in writable_accounts[:15]:
                print(f"\n   📋 {pubkey}")
                
                acc_result = await rpc_call(session, "getAccountInfo", [pubkey, {"encoding": "base64"}])
                acc_info = acc_result.get("result", {})
                
                if acc_info.get("value"):
                    owner = acc_info["value"].get("owner")
                    data = acc_info["value"].get("data", [])
                    
                    print(f"      Owner: {owner}")
                    
                    if data and data[0]:
                        data_bytes = base64.b64decode(data[0])
                        print(f"      Data: {len(data_bytes)} bytes")
                        
                        # 检查是否包含用户地址或 NFT
                        target_bytes = b58decode(TARGET_ADDRESS)
                        nft_bytes = b58decode(NFT_MINT)
                        
                        if target_bytes in data_bytes:
                            pos = data_bytes.find(target_bytes)
                            print(f"      ✅ 包含用户地址! offset: {pos}")
                        
                        if nft_bytes in data_bytes:
                            pos = data_bytes.find(nft_bytes)
                            print(f"      ✅ 包含 NFT Mint! offset: {pos}")
                        
                        # 检查 jupSOL
                        jupsol_bytes = b58decode("jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v")
                        if jupsol_bytes in data_bytes:
                            pos = data_bytes.find(jupsol_bytes)
                            print(f"      ✅ 包含 jupSOL mint! offset: {pos}")
                else:
                    print(f"      (账户为空或已关闭)")
                
                await asyncio.sleep(0.2)
            
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
