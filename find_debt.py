#!/usr/bin/env python3
"""
查找 Jupiter Multiply 仓位的债务数据
债务应该存储在 Kamino Lending 或其他借贷协议中
"""

import asyncio
import aiohttp
import base64
import struct
from base58 import b58decode, b58encode

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"
NFT_MINT = "8919DKJ49CFcH96cVDnjpJopYeWVpJ9sVunkV3Dpq4HD"

RPC_URL = "https://api.mainnet-beta.solana.com"

# 官方债务数据
EXPECTED_DEBT_SOL = 6120.67
EXPECTED_DEBT_RAW = int(6120.67 * 1e9)  # 6120670000000

# 借贷协议 Program IDs
LENDING_PROGRAMS = [
    ("KLend2g3cP87ber41SJq1PqSXW3Mc1RRdLnMH7VPZ5M", "Kamino Lending"),
    ("MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA", "Marginfi"),
]


async def rpc_call(session: aiohttp.ClientSession, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
            return await response.json()
    except Exception as e:
        return {"error": str(e)}


def search_value_in_data(data: bytes, target: float, decimals: int = 9, tolerance: float = 1.0) -> list:
    """在数据中搜索目标值"""
    target_raw = int(target * (10 ** decimals))
    tolerance_raw = int(tolerance * (10 ** decimals))
    results = []
    
    for offset in range(len(data) - 7):
        try:
            val = struct.unpack('<Q', data[offset:offset+8])[0]
            if abs(val - target_raw) <= tolerance_raw:
                results.append({
                    "offset": offset,
                    "raw": val,
                    "decoded": val / (10 ** decimals),
                })
        except:
            pass
    
    return results


async def main():
    print("=" * 70)
    print("🔍 查找 Jupiter Multiply 债务数据")
    print(f"   目标: {EXPECTED_DEBT_SOL:.2f} SOL")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        
        # 1. 首先获取最近交易中涉及的所有账户
        print("\n📊 从最近交易中查找债务相关账户...")
        
        # 获取 NFT token account 的交易
        nft_token_account = "CVxBujMbbNszmGygDbi12Dy8NCAjw5dYNeX3z6NmhjKS"
        result = await rpc_call(session, "getSignaturesForAddress", [
            nft_token_account,
            {"limit": 3}
        ])
        
        signatures = result.get("result", [])
        all_accounts = set()
        
        for sig_info in signatures[:1]:  # 只分析最近一笔
            sig = sig_info["signature"]
            print(f"\n   分析交易: {sig[:40]}...")
            
            tx_result = await rpc_call(session, "getTransaction", [
                sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ])
            
            tx = tx_result.get("result")
            if tx:
                message = tx.get("transaction", {}).get("message", {})
                account_keys = message.get("accountKeys", [])
                
                for acc in account_keys:
                    pubkey = acc.get("pubkey") if isinstance(acc, dict) else acc
                    all_accounts.add(pubkey)
        
        print(f"   找到 {len(all_accounts)} 个相关账户")
        
        # 2. 在所有账户中搜索债务值
        print(f"\n📊 在账户中搜索债务值 ({EXPECTED_DEBT_SOL:.2f} SOL)...")
        
        debt_found = []
        
        for addr in list(all_accounts)[:30]:  # 检查前30个账户
            result = await rpc_call(session, "getAccountInfo", [addr, {"encoding": "base64"}])
            
            if result.get("result", {}).get("value"):
                value = result["result"]["value"]
                owner = value.get("owner")
                data = value.get("data", [])
                
                if data and data[0]:
                    data_bytes = base64.b64decode(data[0])
                    
                    # 搜索债务值
                    matches = search_value_in_data(data_bytes, EXPECTED_DEBT_SOL, 9, 1.0)
                    
                    if matches:
                        debt_found.append({
                            "address": addr,
                            "owner": owner,
                            "matches": matches,
                            "data_length": len(data_bytes)
                        })
                        
                        print(f"\n   ✅ 找到匹配!")
                        print(f"      账户: {addr}")
                        print(f"      Owner: {owner}")
                        for m in matches:
                            print(f"      offset {m['offset']}: {m['decoded']:.6f} SOL")
            
            await asyncio.sleep(0.1)
        
        # 3. 搜索 Kamino Lending 账户
        print(f"\n📊 搜索 Kamino Lending 账户...")
        
        for program_id, program_name in LENDING_PROGRAMS:
            print(f"\n   检查 {program_name}...")
            
            # 用用户地址搜索
            for offset in [8, 32, 40, 72, 104]:
                result = await rpc_call(session, "getProgramAccounts", [
                    program_id,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"memcmp": {"offset": offset, "bytes": TARGET_ADDRESS}}
                        ]
                    }
                ])
                
                if "error" not in result:
                    accounts = result.get("result", [])
                    if accounts:
                        print(f"      ✅ offset {offset}: 找到 {len(accounts)} 个账户")
                        
                        for acc in accounts[:3]:
                            addr = acc["pubkey"]
                            data = base64.b64decode(acc["account"]["data"][0])
                            
                            # 搜索债务值
                            matches = search_value_in_data(data, EXPECTED_DEBT_SOL, 9, 10.0)
                            
                            if matches:
                                print(f"\n         账户: {addr}")
                                for m in matches:
                                    print(f"         offset {m['offset']}: {m['decoded']:.6f} SOL")
                
                await asyncio.sleep(0.5)
        
        # 4. 汇总
        print(f"\n" + "=" * 70)
        print("📋 债务数据搜索结果")
        print("=" * 70)
        
        if debt_found:
            print(f"\n✅ 找到 {len(debt_found)} 个包含债务数据的账户:")
            for item in debt_found:
                print(f"\n   账户: {item['address']}")
                print(f"   Owner: {item['owner']}")
                print(f"   数据长度: {item['data_length']} bytes")
                for m in item['matches']:
                    print(f"   债务 @ offset {m['offset']}: {m['decoded']:.6f} SOL")
        else:
            print(f"\n❌ 未找到精确匹配的债务数据")
            print(f"   债务可能:")
            print(f"   1. 使用不同的精度存储")
            print(f"   2. 存储在 Kamino 的 Obligation 账户中 (需要完整 IDL)")
            print(f"   3. 通过计算得出 (抵押品 * LTV / 汇率)")


if __name__ == "__main__":
    asyncio.run(main())
