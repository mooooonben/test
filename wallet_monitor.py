#!/usr/bin/env python3
"""
多链钱包余额监控工具
支持 Ethereum (ETH), Solana (SOL), Aptos (APT)
包括原生代币、其他代币和 DeFi 仓位（含借贷详情）
"""

import asyncio
import aiohttp
import yaml
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path


@dataclass
class TokenBalance:
    """代币余额数据类"""
    symbol: str
    name: str
    balance: float
    contract_address: Optional[str] = None
    decimals: int = 18
    usd_value: Optional[float] = None
    logo_url: Optional[str] = None
    token_type: str = "token"  # token, lp, staking, lending, collateral, debt


@dataclass 
class LendingPosition:
    """借贷仓位详情"""
    protocol: str
    supplied: List[TokenBalance] = field(default_factory=list)  # 存入/抵押
    borrowed: List[TokenBalance] = field(default_factory=list)  # 借出/债务
    total_supplied_usd: float = 0.0
    total_borrowed_usd: float = 0.0
    health_factor: Optional[float] = None
    net_worth_usd: float = 0.0


@dataclass 
class DeFiPosition:
    """DeFi 仓位数据类"""
    protocol: str
    position_type: str  # staking, lending, liquidity, farming
    tokens: List[TokenBalance] = field(default_factory=list)
    total_usd_value: Optional[float] = None
    apy: Optional[float] = None
    lending_details: Optional[LendingPosition] = None  # 借贷详情


@dataclass
class WalletBalance:
    """钱包余额数据类"""
    chain: str
    address: str
    name: str
    native_balance: float
    native_symbol: str
    timestamp: datetime
    native_usd_value: Optional[float] = None
    tokens: List[TokenBalance] = field(default_factory=list)
    defi_positions: List[DeFiPosition] = field(default_factory=list)


class ChainMonitor(ABC):
    """链监控基类"""
    
    def __init__(self, config: dict):
        self.config = config
    
    @abstractmethod
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance], List[DeFiPosition]]:
        """获取钱包余额，返回 (原生代币余额, 其他代币列表, DeFi仓位列表)"""
        pass
    
    @property
    @abstractmethod
    def chain_name(self) -> str:
        """链名称"""
        pass
    
    @property
    @abstractmethod
    def symbol(self) -> str:
        """原生代币符号"""
        pass


class EthereumMonitor(ChainMonitor):
    """Ethereum 链监控 - 支持 ERC-20 代币和 DeFi（含借贷详情）"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_delay = config.get("api_delay", 0.1)  # 默认 100ms 延迟
    
    # 常见 ERC-20 代币
    KNOWN_TOKENS = {
        "0xdAC17F958D2ee523a2206206994597C13D831ec7": ("USDT", "Tether USD", 6),
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": ("USDC", "USD Coin", 6),
        "0x6B175474E89094C44Da98b954EescdeCB5": ("DAI", "Dai Stablecoin", 18),
        "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": ("WBTC", "Wrapped BTC", 8),
        "0x514910771AF9Ca656af840dff83E8264EcF986CA": ("LINK", "Chainlink", 18),
        "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984": ("UNI", "Uniswap", 18),
        "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0": ("MATIC", "Polygon", 18),
        "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE": ("SHIB", "Shiba Inu", 18),
        "0x6982508145454Ce325dDbE47a25d4ec3d2311933": ("PEPE", "Pepe", 18),
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": ("WETH", "Wrapped Ether", 18),
        "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9": ("AAVE", "Aave", 18),
        "0x4d224452801ACEd8B2F0aebE155379bb5D594381": ("APE", "ApeCoin", 18),
    }
    
    # Staking 代币 (Lido, Rocket Pool, etc.)
    STAKING_TOKENS = {
        # Lido
        "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84": ("stETH", "Lido Staked ETH", 18, "Lido", "staking"),
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0": ("wstETH", "Wrapped stETH", 18, "Lido", "staking"),
        # Rocket Pool
        "0xae78736Cd615f374D3085123A210448E74Fc6393": ("rETH", "Rocket Pool ETH", 18, "Rocket Pool", "staking"),
        # Coinbase
        "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704": ("cbETH", "Coinbase Wrapped Staked ETH", 18, "Coinbase", "staking"),
        # Frax
        "0x5E8422345238F34275888049021821E8E08CAa1f": ("frxETH", "Frax Ether", 18, "Frax", "staking"),
        "0xac3E018457B222d93114458476f3E3416Abbe38F": ("sfrxETH", "Staked Frax Ether", 18, "Frax", "staking"),
        # EtherFi (正确地址)
        "0x35fA164735182de50811E8e2E824cFb9B6118ac2": ("eETH", "ether.fi Staked ETH", 18, "EtherFi", "staking"),
        "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee": ("weETH", "Wrapped eETH", 18, "EtherFi", "staking"),
        # EigenLayer
        "0xec53bF9167f50cDEB3Ae105f56099aaaB9061F83": ("EIGEN", "EigenLayer", 18, "EigenLayer", "staking"),
        # ETHFI 治理代币
        "0xFe0c30065B384F05761f15d0CC899D4F9F9Cc0eB": ("ETHFI", "ether.fi Governance", 18, "EtherFi", "token"),
        # Curve LP
        "0x06325440D014e39736583c165C2963BA99fAf14E": ("steCRV", "Curve stETH/ETH LP", 18, "Curve", "liquidity"),
        # Convex
        "0x62B9c7356A2Dc64a1969e19C23e4f579F9810Aa7": ("cvxCRV", "Convex CRV", 18, "Convex", "staking"),
    }
    
    # ========== Aave V3 代币 ==========
    # 抵押品代币 (aTokens) - 存入资产获得
    AAVE_V3_ATOKENS = {
        "0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8": ("aEthWETH", "Aave ETH WETH", 18, "WETH"),
        "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c": ("aEthUSDC", "Aave ETH USDC", 6, "USDC"),
        "0x23878914EFE38d27C4D67Ab83ed1b93A74D4086a": ("aEthUSDT", "Aave ETH USDT", 6, "USDT"),
        "0x018008bfb33d285247A21d44E50697654f754e63": ("aEthDAI", "Aave ETH DAI", 18, "DAI"),
        "0x5Ee5bf7ae06D1Be5997A1A72006FE6C607eC6DE8": ("aEthWBTC", "Aave ETH WBTC", 8, "WBTC"),
        "0x0B925eD163218f6662a35e0f0371Ac234f9E9371": ("aEthwstETH", "Aave ETH wstETH", 18, "wstETH"),
        "0xBdfa7b7893081B35Fb54027489e2Bc7A38275129": ("aEthweETH", "Aave ETH weETH", 18, "weETH"),
        "0x7B95Ec873268a6BFC6427e7a28e396Db9D0ebc65": ("aEthrETH", "Aave ETH rETH", 18, "rETH"),
        "0xA700b4eB416Be35b2911fd5Dee80678ff64fF6C9": ("aEthLINK", "Aave ETH LINK", 18, "LINK"),
        "0xF6D2224916DDFbbab6e6bd0D1B7034f4Ae0CaB18": ("aEthAAVE", "Aave ETH AAVE", 18, "AAVE"),
    }
    
    # 债务代币 (Variable Debt Tokens) - 借款产生
    AAVE_V3_DEBT_TOKENS = {
        "0xeA51d7853EEFb32b6ee06b1C12E6dcCA88Be0fFE": ("vDebtWETH", "Aave Variable Debt WETH", 18, "WETH"),
        "0x72E95b8931767C79bA4EeE721354d6E99a61D004": ("vDebtUSDC", "Aave Variable Debt USDC", 6, "USDC"),
        "0x6df1C1E379bC5a00a7b4C6e67A203333772f45A8": ("vDebtUSDT", "Aave Variable Debt USDT", 6, "USDT"),
        "0xcF8d0c70c850859266f5C338b38F9D663181C314": ("vDebtDAI", "Aave Variable Debt DAI", 18, "DAI"),
        "0x40aAbEf1aa8f0eEc637E0E7d92fbfFB2F26A8b7B": ("vDebtWBTC", "Aave Variable Debt WBTC", 8, "WBTC"),
        "0xD5c3E3B566f73AA6A62a1a349BB5370a21b4c5C0": ("vDebtwstETH", "Aave Variable Debt wstETH", 18, "wstETH"),
        "0xeEDaE28f271F1df4B67a69E94fA69CCec5676b96": ("vDebtweETH", "Aave Variable Debt weETH", 18, "weETH"),
        "0x64b761D848206f447Fe2dd461b0c635Ec39EbB27": ("vDebtLINK", "Aave Variable Debt LINK", 18, "LINK"),
    }
    
    # Compound V3 (Comet)
    COMPOUND_V3_TOKENS = {
        "0xc3d688B66703497DAA19211EEdff47f25384cdc3": ("cUSDCv3", "Compound USDC", 6, "Compound V3"),
        "0xA17581A9E3356d9A858b789D68B4d866e593aE94": ("cWETHv3", "Compound WETH", 18, "Compound V3"),
    }
    
    @property
    def chain_name(self) -> str:
        return "Ethereum"
    
    @property
    def symbol(self) -> str:
        return "ETH"
    
    async def get_native_balance(self, session: aiohttp.ClientSession, address: str) -> float:
        """获取 ETH 余额"""
        rpc_url = self.config.get("rpc_url", "https://eth.llamarpc.com")
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [address, "latest"],
            "id": 1
        }
        
        async with session.post(rpc_url, json=payload) as response:
            data = await response.json()
            if "result" in data:
                balance_wei = int(data["result"], 16)
                return balance_wei / 1e18
            return 0.0
    
    async def get_token_balance(self, session: aiohttp.ClientSession, 
                                 address: str, token_address: str, 
                                 decimals: int) -> float:
        """获取单个 ERC-20 代币余额"""
        rpc_url = self.config.get("rpc_url", "https://eth.llamarpc.com")
        
        data = f"0x70a08231000000000000000000000000{address[2:].lower()}"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": token_address, "data": data}, "latest"],
            "id": 1
        }
        
        try:
            async with session.post(rpc_url, json=payload) as response:
                result = await response.json()
                if "result" in result and result["result"] not in ["0x", "0x0"]:
                    balance = int(result["result"], 16)
                    return balance / (10 ** decimals)
        except Exception:
            pass
        return 0.0
    
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance], List[DeFiPosition]]:
        """获取 ETH、ERC-20 代币和 DeFi 仓位"""
        tokens = []
        defi_positions = []
        staking_by_protocol: Dict[str, List[TokenBalance]] = {}
        
        # Aave 借贷详情
        aave_supplied: List[TokenBalance] = []
        aave_borrowed: List[TokenBalance] = []
        
        async with aiohttp.ClientSession() as session:
            # 获取 ETH 余额
            native_balance = await self.get_native_balance(session, address)
            
            # 获取常见 ERC-20 代币余额
            for token_addr, (symbol, name, decimals) in self.KNOWN_TOKENS.items():
                try:
                    balance = await self.get_token_balance(session, address, token_addr, decimals)
                    if balance > 0:
                        tokens.append(TokenBalance(
                            symbol=symbol,
                            name=name,
                            balance=balance,
                            contract_address=token_addr,
                            decimals=decimals,
                            token_type="token"
                        ))
                    await asyncio.sleep(self.api_delay)  # API 限流延迟
                except Exception:
                    continue
            
            # 获取 Staking 代币余额
            for token_addr, (symbol, name, decimals, protocol, pos_type) in self.STAKING_TOKENS.items():
                try:
                    balance = await self.get_token_balance(session, address, token_addr, decimals)
                    if balance > 0:
                        token = TokenBalance(
                            symbol=symbol,
                            name=name,
                            balance=balance,
                            contract_address=token_addr,
                            decimals=decimals,
                            token_type=pos_type
                        )
                        key = f"{protocol}|{pos_type}"
                        if key not in staking_by_protocol:
                            staking_by_protocol[key] = []
                        staking_by_protocol[key].append(token)
                    await asyncio.sleep(self.api_delay)  # API 限流延迟
                except Exception:
                    continue
            
            # ========== Aave V3 抵押品 (aTokens) ==========
            for token_addr, (symbol, name, decimals, underlying) in self.AAVE_V3_ATOKENS.items():
                try:
                    balance = await self.get_token_balance(session, address, token_addr, decimals)
                    if balance > 0:
                        aave_supplied.append(TokenBalance(
                            symbol=underlying,  # 显示底层资产符号
                            name=f"Aave 抵押 {underlying}",
                            balance=balance,
                            contract_address=token_addr,
                            decimals=decimals,
                            token_type="collateral"
                        ))
                    await asyncio.sleep(self.api_delay)  # API 限流延迟
                except Exception:
                    continue
            
            # ========== Aave V3 债务 (Variable Debt Tokens) ==========
            for token_addr, (symbol, name, decimals, underlying) in self.AAVE_V3_DEBT_TOKENS.items():
                try:
                    balance = await self.get_token_balance(session, address, token_addr, decimals)
                    if balance > 0:
                        aave_borrowed.append(TokenBalance(
                            symbol=underlying,  # 显示底层资产符号
                            name=f"Aave 债务 {underlying}",
                            balance=balance,
                            contract_address=token_addr,
                            decimals=decimals,
                            token_type="debt"
                        ))
                    await asyncio.sleep(self.api_delay)  # API 限流延迟
                except Exception:
                    continue
            
            # 创建 Staking DeFi 仓位
            for key, tokens_list in staking_by_protocol.items():
                protocol, pos_type = key.split("|")
                defi_positions.append(DeFiPosition(
                    protocol=protocol,
                    position_type=pos_type,
                    tokens=tokens_list
                ))
            
            # 创建 Aave 借贷仓位
            if aave_supplied or aave_borrowed:
                lending_details = LendingPosition(
                    protocol="Aave V3",
                    supplied=aave_supplied,
                    borrowed=aave_borrowed
                )
                defi_positions.append(DeFiPosition(
                    protocol="Aave V3",
                    position_type="lending",
                    tokens=aave_supplied + aave_borrowed,
                    lending_details=lending_details
                ))
        
        return native_balance, tokens, defi_positions


class SolanaMonitor(ChainMonitor):
    """Solana 链监控 - 支持 SPL 代币和 DeFi"""
    
    _token_list_cache: Optional[Dict[str, dict]] = None
    _cache_time: Optional[datetime] = None
    
    DEFI_TOKENS = {
        "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": ("mSOL", "Marinade Staked SOL", 9, "Marinade", "staking"),
        "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": ("JitoSOL", "Jito Staked SOL", 9, "Jito", "staking"),
        "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": ("jupSOL", "Jupiter Staked SOL", 9, "Jupiter", "staking"),
        "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1": ("bSOL", "BlazeStake Staked SOL", 9, "BlazeStake", "staking"),
        "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm": ("INF", "Sanctum Infinity", 9, "Sanctum", "staking"),
        "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": ("stSOL", "Lido Staked SOL", 9, "Lido", "staking"),
    }
    
    LP_PATTERNS = ["LP", "AMM", "POOL", "Liquidity"]
    STAKE_PATTERNS = ["staked", "stSOL", "mSOL", "jitoSOL", "bSOL", "jupSOL"]
    
    @property
    def chain_name(self) -> str:
        return "Solana"
    
    @property
    def symbol(self) -> str:
        return "SOL"
    
    async def _load_token_list(self, session: aiohttp.ClientSession) -> Dict[str, dict]:
        if (self._token_list_cache is not None and 
            self._cache_time is not None and
            (datetime.now() - self._cache_time).seconds < 3600):
            return self._token_list_cache
        
        try:
            url = "https://token.jup.ag/all"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    tokens = await response.json()
                    SolanaMonitor._token_list_cache = {t["address"]: t for t in tokens}
                    SolanaMonitor._cache_time = datetime.now()
                    return SolanaMonitor._token_list_cache
        except Exception:
            pass
        return {}
    
    def _classify_token(self, symbol: str, name: str, mint: str) -> str:
        upper_name = name.upper()
        upper_symbol = symbol.upper()
        
        if any(p in upper_name or p in upper_symbol for p in self.LP_PATTERNS):
            return "liquidity"
        if any(p.lower() in symbol.lower() or p.lower() in name.lower() for p in self.STAKE_PATTERNS):
            return "staking"
        if mint in self.DEFI_TOKENS:
            return self.DEFI_TOKENS[mint][4]
        return "token"
    
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance], List[DeFiPosition]]:
        rpc_url = self.config.get("rpc_url", "https://api.mainnet-beta.solana.com")
        tokens = []
        defi_positions = []
        defi_by_protocol: Dict[str, List[TokenBalance]] = {}
        native_balance = 0.0
        
        async with aiohttp.ClientSession() as session:
            token_list = await self._load_token_list(session)
            
            payload = {"jsonrpc": "2.0", "method": "getBalance", "params": [address], "id": 1}
            async with session.post(rpc_url, json=payload) as response:
                data = await response.json()
                if "result" in data:
                    native_balance = data["result"]["value"] / 1e9
            
            payload = {
                "jsonrpc": "2.0",
                "method": "getTokenAccountsByOwner",
                "params": [address, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}, {"encoding": "jsonParsed"}],
                "id": 2
            }
            
            async with session.post(rpc_url, json=payload) as response:
                data = await response.json()
                if "result" in data:
                    for account in data["result"].get("value", []):
                        try:
                            parsed = account["account"]["data"]["parsed"]["info"]
                            token_amount = parsed["tokenAmount"]
                            balance = float(token_amount["uiAmount"] or 0)
                            
                            if balance > 0:
                                mint = parsed["mint"]
                                token_info = token_list.get(mint, {})
                                symbol = token_info.get("symbol", mint[:8])
                                name = token_info.get("name", "Unknown Token")
                                
                                if mint in self.DEFI_TOKENS:
                                    symbol, name, _, protocol, pos_type = self.DEFI_TOKENS[mint]
                                    token = TokenBalance(symbol=symbol, name=name, balance=balance,
                                                        contract_address=mint, decimals=int(token_amount["decimals"]),
                                                        token_type=pos_type)
                                    key = f"{protocol}|{pos_type}"
                                    if key not in defi_by_protocol:
                                        defi_by_protocol[key] = []
                                    defi_by_protocol[key].append(token)
                                else:
                                    token_type = self._classify_token(symbol, name, mint)
                                    token = TokenBalance(symbol=symbol, name=name, balance=balance,
                                                        contract_address=mint, decimals=int(token_amount["decimals"]),
                                                        token_type=token_type)
                                    if token_type in ["staking", "liquidity", "lending"]:
                                        key = f"Unknown|{token_type}"
                                        if key not in defi_by_protocol:
                                            defi_by_protocol[key] = []
                                        defi_by_protocol[key].append(token)
                                    else:
                                        tokens.append(token)
                        except Exception:
                            continue
            
            for key, tokens_list in defi_by_protocol.items():
                protocol, pos_type = key.split("|")
                defi_positions.append(DeFiPosition(protocol=protocol, position_type=pos_type, tokens=tokens_list))
        
        return native_balance, tokens, defi_positions


class AptosMonitor(ChainMonitor):
    """Aptos 链监控"""
    
    @property
    def chain_name(self) -> str:
        return "Aptos"
    
    @property
    def symbol(self) -> str:
        return "APT"
    
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance], List[DeFiPosition]]:
        api_url = self.config.get("api_url", "https://fullnode.mainnet.aptoslabs.com/v1")
        tokens = []
        defi_positions = []
        native_balance = 0.0
        
        async with aiohttp.ClientSession() as session:
            url = f"{api_url}/accounts/{address}/resources"
            
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        resources = await response.json()
                        
                        for resource in resources:
                            res_type = resource.get("type", "")
                            
                            if "0x1::coin::CoinStore<" in res_type:
                                try:
                                    coin_type = res_type.split("<")[1].rstrip(">")
                                    value = int(resource["data"]["coin"]["value"])
                                    
                                    if coin_type == "0x1::aptos_coin::AptosCoin":
                                        native_balance = value / 1e8
                                    else:
                                        if value > 0:
                                            symbol = self._parse_coin_symbol(coin_type)
                                            tokens.append(TokenBalance(
                                                symbol=symbol, name=coin_type.split("::")[-1],
                                                balance=value / 1e8, contract_address=coin_type, decimals=8
                                            ))
                                except Exception:
                                    continue
            except Exception as e:
                print(f"APT API Error: {e}")
        
        return native_balance, tokens, defi_positions
    
    def _parse_coin_symbol(self, coin_type: str) -> str:
        try:
            parts = coin_type.split("::")
            if len(parts) >= 3:
                return parts[-1][:10]
        except Exception:
            pass
        return coin_type[:10] + "..."


class PriceService:
    """价格服务"""
    
    COINGECKO_IDS = {
        "ETH": "ethereum", "WETH": "ethereum",
        "SOL": "solana",
        "APT": "aptos",
        "USDT": "tether", "USDC": "usd-coin", "DAI": "dai",
        "WBTC": "wrapped-bitcoin", "BTC": "bitcoin",
        "LINK": "chainlink", "UNI": "uniswap", "AAVE": "aave",
        "MATIC": "matic-network", "SHIB": "shiba-inu", "PEPE": "pepe",
        "stETH": "staked-ether", "wstETH": "wrapped-steth",
        "rETH": "rocket-pool-eth", "cbETH": "coinbase-wrapped-staked-eth",
        "frxETH": "frax-ether", "sfrxETH": "staked-frax-ether",
        "eETH": "ether-fi-staked-eth", "weETH": "wrapped-eeth",
        "EIGEN": "eigenlayer", "ETHFI": "ether-fi",
        "mSOL": "msol", "JitoSOL": "jito-staked-sol",
        "bSOL": "blazestake-staked-sol", "stSOL": "lido-staked-sol",
    }
    
    def __init__(self):
        self.prices: Dict[str, float] = {}
        self.last_update: Optional[datetime] = None
    
    async def update_prices(self) -> Dict[str, float]:
        ids = ",".join(set(self.COINGECKO_IDS.values()))
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        data = await response.json()
                        for symbol, coin_id in self.COINGECKO_IDS.items():
                            if coin_id in data and "usd" in data[coin_id]:
                                self.prices[symbol] = data[coin_id]["usd"]
                        self.last_update = datetime.now()
        except Exception as e:
            print(f"⚠️  获取价格失败: {e}")
        
        return self.prices
    
    def get_price(self, symbol: str) -> Optional[float]:
        if symbol.upper() in ["USDT", "USDC", "DAI", "BUSD", "TUSD"]:
            return 1.0
        return self.prices.get(symbol) or self.prices.get(symbol.upper())


class WalletMonitor:
    """钱包监控主类"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.monitors: Dict[str, ChainMonitor] = {}
        self.price_service = PriceService()
        self._init_monitors()
    
    def _load_config(self, config_path: str) -> dict:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _init_monitors(self):
        # 获取全局 API 延迟配置
        api_delay = self.config.get("api_delay", 0.1)
        
        if "ethereum" in self.config:
            eth_config = self.config["ethereum"].copy()
            eth_config["api_delay"] = api_delay
            self.monitors["ethereum"] = EthereumMonitor(eth_config)
        if "solana" in self.config:
            sol_config = self.config["solana"].copy()
            sol_config["api_delay"] = api_delay
            self.monitors["solana"] = SolanaMonitor(sol_config)
        if "aptos" in self.config:
            apt_config = self.config["aptos"].copy()
            apt_config["api_delay"] = api_delay
            self.monitors["aptos"] = AptosMonitor(apt_config)
    
    async def check_balance(self, chain: str, wallet: dict) -> Optional[WalletBalance]:
        monitor = self.monitors.get(chain)
        if not monitor:
            return None
        
        try:
            native_balance, tokens, defi_positions = await monitor.get_balance(wallet["address"])
            price = self.price_service.get_price(monitor.symbol)
            native_usd = native_balance * price if price else None
            
            # 计算代币 USD 价值
            for token in tokens:
                token_price = self.price_service.get_price(token.symbol)
                if token_price:
                    token.usd_value = token.balance * token_price
            
            # 计算 DeFi 仓位 USD 价值
            for position in defi_positions:
                total = 0.0
                
                # 如果有借贷详情，计算详细价值
                if position.lending_details:
                    ld = position.lending_details
                    
                    # 计算抵押品价值
                    for token in ld.supplied:
                        token_price = self.price_service.get_price(token.symbol)
                        if token_price:
                            token.usd_value = token.balance * token_price
                            ld.total_supplied_usd += token.usd_value
                    
                    # 计算债务价值
                    for token in ld.borrowed:
                        token_price = self.price_service.get_price(token.symbol)
                        if token_price:
                            token.usd_value = token.balance * token_price
                            ld.total_borrowed_usd += token.usd_value
                    
                    # 计算净值
                    ld.net_worth_usd = ld.total_supplied_usd - ld.total_borrowed_usd
                    
                    # 计算健康因子 (简化计算，假设清算阈值 80%)
                    if ld.total_borrowed_usd > 0:
                        ld.health_factor = (ld.total_supplied_usd * 0.8) / ld.total_borrowed_usd
                    
                    position.total_usd_value = ld.net_worth_usd
                else:
                    for token in position.tokens:
                        token_price = self.price_service.get_price(token.symbol)
                        if token_price:
                            token.usd_value = token.balance * token_price
                            total += token.usd_value
                    position.total_usd_value = total if total > 0 else None
            
            return WalletBalance(
                chain=monitor.chain_name,
                address=wallet["address"],
                name=wallet.get("name", wallet["address"][:10] + "..."),
                native_balance=native_balance,
                native_symbol=monitor.symbol,
                timestamp=datetime.now(),
                native_usd_value=native_usd,
                tokens=tokens,
                defi_positions=defi_positions
            )
        except Exception as e:
            print(f"❌ 获取 {chain} 钱包 {wallet.get('name')} 失败: {e}")
            return None
    
    async def check_all_balances(self) -> List[WalletBalance]:
        tasks = []
        for chain in self.monitors:
            wallets = self.config.get(chain, {}).get("wallets", [])
            for wallet in wallets:
                tasks.append(self.check_balance(chain, wallet))
        
        balances = await asyncio.gather(*tasks)
        return [b for b in balances if b is not None]
    
    def _format_number(self, num: float) -> str:
        if num >= 1_000_000:
            return f"{num:,.0f}"
        elif num >= 1:
            return f"{num:,.4f}"
        else:
            return f"{num:,.6f}"
    
    def _format_balance(self, balance: WalletBalance) -> str:
        lines = []
        
        lines.append(f"\n  📍 [{balance.chain}] {balance.name}")
        
        # 原生代币
        usd = f" (${balance.native_usd_value:,.2f})" if balance.native_usd_value else ""
        lines.append(f"     ├─ 💰 {self._format_number(balance.native_balance)} {balance.native_symbol}{usd}")
        
        # 普通代币
        if balance.tokens:
            lines.append(f"     │")
            lines.append(f"     ├─ 🪙 代币:")
            sorted_tokens = sorted(balance.tokens, key=lambda t: t.usd_value or 0, reverse=True)
            for token in sorted_tokens[:15]:
                usd = f" (${token.usd_value:,.2f})" if token.usd_value else ""
                lines.append(f"     │  └─ {self._format_number(token.balance)} {token.symbol}{usd}")
            if len(balance.tokens) > 15:
                lines.append(f"     │  └─ ... 还有 {len(balance.tokens) - 15} 个代币")
        
        # DeFi 仓位
        if balance.defi_positions:
            lines.append(f"     │")
            lines.append(f"     └─ 🏦 DeFi 仓位:")
            
            for pos in balance.defi_positions:
                # 借贷协议特殊处理
                if pos.lending_details:
                    ld = pos.lending_details
                    lines.append(f"        │")
                    lines.append(f"        ├─ 🏛️ {pos.protocol} [借贷]")
                    
                    # 抵押品
                    if ld.supplied:
                        lines.append(f"        │  ├─ 💎 抵押品 (Collateral): ${ld.total_supplied_usd:,.2f}")
                        for token in ld.supplied:
                            usd = f" (${token.usd_value:,.2f})" if token.usd_value else ""
                            lines.append(f"        │  │  └─ {self._format_number(token.balance)} {token.symbol}{usd}")
                    
                    # 债务
                    if ld.borrowed:
                        lines.append(f"        │  ├─ 💸 债务 (Debt): ${ld.total_borrowed_usd:,.2f}")
                        for token in ld.borrowed:
                            usd = f" (${token.usd_value:,.2f})" if token.usd_value else ""
                            lines.append(f"        │  │  └─ {self._format_number(token.balance)} {token.symbol}{usd}")
                    
                    # 净值和健康因子
                    lines.append(f"        │  ├─ 📊 净值: ${ld.net_worth_usd:,.2f}")
                    if ld.health_factor:
                        hf_emoji = "🟢" if ld.health_factor > 1.5 else "🟡" if ld.health_factor > 1.2 else "🔴"
                        lines.append(f"        │  └─ {hf_emoji} 健康因子: {ld.health_factor:.2f}")
                else:
                    # 其他 DeFi 仓位
                    type_emoji = {
                        "staking": "🥩", "lending": "🏛️",
                        "liquidity": "💧", "farming": "🌾"
                    }.get(pos.position_type, "📊")
                    
                    usd = f" (${pos.total_usd_value:,.2f})" if pos.total_usd_value else ""
                    lines.append(f"        ├─ {type_emoji} {pos.protocol} [{pos.position_type}]{usd}")
                    for token in pos.tokens:
                        t_usd = f" (${token.usd_value:,.2f})" if token.usd_value else ""
                        lines.append(f"        │  └─ {self._format_number(token.balance)} {token.symbol}{t_usd}")
        
        return "\n".join(lines)
    
    async def run_once(self) -> List[WalletBalance]:
        print(f"\n{'='*70}")
        print(f"⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        print("📈 获取代币价格...")
        await self.price_service.update_prices()
        
        print("🔍 查询钱包余额 (包括 DeFi 借贷详情)...\n")
        balances = await self.check_all_balances()
        
        total_usd = 0.0
        total_defi = 0.0
        total_debt = 0.0
        
        for balance in balances:
            print(self._format_balance(balance))
            
            if balance.native_usd_value:
                total_usd += balance.native_usd_value
            for token in balance.tokens:
                if token.usd_value:
                    total_usd += token.usd_value
            for pos in balance.defi_positions:
                if pos.lending_details:
                    total_usd += pos.lending_details.net_worth_usd
                    total_defi += pos.lending_details.total_supplied_usd
                    total_debt += pos.lending_details.total_borrowed_usd
                elif pos.total_usd_value:
                    total_usd += pos.total_usd_value
                    total_defi += pos.total_usd_value
        
        print(f"\n{'─'*70}")
        print(f"💰 总资产净值: ${total_usd:,.2f} USD")
        if total_defi > 0:
            print(f"🏦 DeFi 存入: ${total_defi:,.2f} USD")
        if total_debt > 0:
            print(f"💸 DeFi 债务: ${total_debt:,.2f} USD")
        print(f"{'='*70}")
        
        return balances
    
    async def run(self):
        interval = self.config.get("monitor_interval", 60)
        print("🚀 钱包余额监控启动 (含 DeFi 借贷详情)")
        print(f"📊 监控链: {', '.join(self.monitors.keys())}")
        print(f"⏱️  间隔: {interval} 秒")
        
        while True:
            try:
                await self.run_once()
            except Exception as e:
                print(f"❌ 错误: {e}")
            await asyncio.sleep(interval)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="多链钱包监控 (含 DeFi 借贷详情)")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    
    try:
        monitor = WalletMonitor(args.config)
        if args.once:
            await monitor.run_once()
        else:
            await monitor.run()
    except FileNotFoundError as e:
        print(f"❌ {e}")
    except KeyboardInterrupt:
        print("\n👋 已停止")


if __name__ == "__main__":
    asyncio.run(main())
