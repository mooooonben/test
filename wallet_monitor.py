#!/usr/bin/env python3
"""
多链钱包余额监控工具
支持 Ethereum (ETH), Solana (SOL), Aptos (APT)
包括原生代币、其他代币和 DeFi 仓位
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
    token_type: str = "token"  # token, lp, staking, lending, nft


@dataclass 
class DeFiPosition:
    """DeFi 仓位数据类"""
    protocol: str
    position_type: str  # staking, lending, liquidity, farming
    tokens: List[TokenBalance]
    total_usd_value: Optional[float] = None
    apy: Optional[float] = None
    health_factor: Optional[float] = None  # 用于借贷协议


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
    """Ethereum 链监控 - 支持 ERC-20 代币和 DeFi"""
    
    # 常见 ERC-20 代币合约地址和信息
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
    
    # DeFi 相关代币 (质押/LP/借贷凭证)
    DEFI_TOKENS = {
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
        # Aave aTokens (v3)
        "0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8": ("aEthWETH", "Aave Ethereum WETH", 18, "Aave V3", "lending"),
        "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c": ("aEthUSDC", "Aave Ethereum USDC", 6, "Aave V3", "lending"),
        "0x23878914EFE38d27C4D67Ab83ed1b93A74D4086a": ("aEthUSDT", "Aave Ethereum USDT", 6, "Aave V3", "lending"),
        # Compound cTokens
        "0x4Ddc2D193948926D02f9B1fE9e1daa0718270ED5": ("cETH", "Compound Ether", 8, "Compound", "lending"),
        "0x39AA39c021dfbaE8faC545936693aC917d5E7563": ("cUSDC", "Compound USD Coin", 8, "Compound", "lending"),
        # Curve LP tokens
        "0x06325440D014e39736583c165C2963BA99fAf14E": ("steCRV", "Curve stETH/ETH LP", 18, "Curve", "liquidity"),
        # Convex
        "0x62B9c7356A2Dc64a1969e19C23e4f579F9810Aa7": ("cvxCRV", "Convex CRV", 18, "Convex", "staking"),
        # EigenLayer
        "0xEC53bF9167f50cDEB3Ae105f56099aaaB9061F83": ("eETH", "ether.fi Staked ETH", 18, "EtherFi", "staking"),
        "0xFe0c30065B384F05761f15d0CC899D4F9F9Cc0eB": ("weETH", "Wrapped eETH", 18, "EtherFi", "staking"),
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
        
        # ERC-20 balanceOf 函数签名
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
        defi_by_protocol: Dict[str, List[TokenBalance]] = {}
        
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
                except Exception:
                    continue
            
            # 获取 DeFi 相关代币余额
            for token_addr, (symbol, name, decimals, protocol, pos_type) in self.DEFI_TOKENS.items():
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
                        
                        # 按协议分组
                        key = f"{protocol}|{pos_type}"
                        if key not in defi_by_protocol:
                            defi_by_protocol[key] = []
                        defi_by_protocol[key].append(token)
                except Exception:
                    continue
            
            # 创建 DeFi 仓位
            for key, tokens_list in defi_by_protocol.items():
                protocol, pos_type = key.split("|")
                defi_positions.append(DeFiPosition(
                    protocol=protocol,
                    position_type=pos_type,
                    tokens=tokens_list
                ))
        
        return native_balance, tokens, defi_positions


class SolanaMonitor(ChainMonitor):
    """Solana 链监控 - 支持 SPL 代币和 DeFi"""
    
    # 缓存 Jupiter 代币列表
    _token_list_cache: Optional[Dict[str, dict]] = None
    _cache_time: Optional[datetime] = None
    
    # 已知的 DeFi/质押代币
    DEFI_TOKENS = {
        # Marinade
        "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": ("mSOL", "Marinade Staked SOL", 9, "Marinade", "staking"),
        # Jito
        "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": ("JitoSOL", "Jito Staked SOL", 9, "Jito", "staking"),
        # Jupiter
        "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": ("jupSOL", "Jupiter Staked SOL", 9, "Jupiter", "staking"),
        # BlazeStake  
        "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1": ("bSOL", "BlazeStake Staked SOL", 9, "BlazeStake", "staking"),
        # Sanctum
        "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm": ("INF", "Sanctum Infinity", 9, "Sanctum", "staking"),
        # Lido (Solana)
        "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": ("stSOL", "Lido Staked SOL", 9, "Lido", "staking"),
        # Raydium LP tokens patterns - 这些需要特殊处理
    }
    
    # DeFi 协议相关关键词
    LP_PATTERNS = ["LP", "AMM", "POOL", "Liquidity"]
    STAKE_PATTERNS = ["staked", "stSOL", "mSOL", "jitoSOL", "bSOL", "jupSOL"]
    
    @property
    def chain_name(self) -> str:
        return "Solana"
    
    @property
    def symbol(self) -> str:
        return "SOL"
    
    async def _load_token_list(self, session: aiohttp.ClientSession) -> Dict[str, dict]:
        """加载并缓存 Jupiter 代币列表"""
        if (self._token_list_cache is not None and 
            self._cache_time is not None and
            (datetime.now() - self._cache_time).seconds < 3600):
            return self._token_list_cache
        
        try:
            url = "https://token.jup.ag/all"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    tokens = await response.json()
                    SolanaMonitor._token_list_cache = {
                        t["address"]: t for t in tokens
                    }
                    SolanaMonitor._cache_time = datetime.now()
                    return SolanaMonitor._token_list_cache
        except Exception:
            pass
        
        return {}
    
    def _classify_token(self, symbol: str, name: str, mint: str) -> str:
        """分类代币类型"""
        upper_name = name.upper()
        upper_symbol = symbol.upper()
        
        # 检查是否是 LP 代币
        if any(p in upper_name or p in upper_symbol for p in self.LP_PATTERNS):
            return "liquidity"
        
        # 检查是否是质押代币
        if any(p.lower() in symbol.lower() or p.lower() in name.lower() for p in self.STAKE_PATTERNS):
            return "staking"
        
        # 检查已知 DeFi 代币
        if mint in self.DEFI_TOKENS:
            return self.DEFI_TOKENS[mint][4]
        
        return "token"
    
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance], List[DeFiPosition]]:
        """获取 SOL、SPL 代币和 DeFi 仓位"""
        rpc_url = self.config.get("rpc_url", "https://api.mainnet-beta.solana.com")
        tokens = []
        defi_positions = []
        defi_by_protocol: Dict[str, List[TokenBalance]] = {}
        native_balance = 0.0
        
        async with aiohttp.ClientSession() as session:
            # 加载代币列表
            token_list = await self._load_token_list(session)
            
            # 获取 SOL 余额
            payload = {
                "jsonrpc": "2.0",
                "method": "getBalance",
                "params": [address],
                "id": 1
            }
            
            async with session.post(rpc_url, json=payload) as response:
                data = await response.json()
                if "result" in data:
                    native_balance = data["result"]["value"] / 1e9
            
            # 获取所有 SPL 代币账户
            payload = {
                "jsonrpc": "2.0",
                "method": "getTokenAccountsByOwner",
                "params": [
                    address,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed"}
                ],
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
                                
                                # 从缓存获取代币信息
                                token_info = token_list.get(mint, {})
                                symbol = token_info.get("symbol", mint[:8])
                                name = token_info.get("name", "Unknown Token")
                                
                                # 检查是否是已知 DeFi 代币
                                if mint in self.DEFI_TOKENS:
                                    symbol, name, _, protocol, pos_type = self.DEFI_TOKENS[mint]
                                    token = TokenBalance(
                                        symbol=symbol,
                                        name=name,
                                        balance=balance,
                                        contract_address=mint,
                                        decimals=int(token_amount["decimals"]),
                                        token_type=pos_type
                                    )
                                    key = f"{protocol}|{pos_type}"
                                    if key not in defi_by_protocol:
                                        defi_by_protocol[key] = []
                                    defi_by_protocol[key].append(token)
                                else:
                                    # 分类代币
                                    token_type = self._classify_token(symbol, name, mint)
                                    
                                    token = TokenBalance(
                                        symbol=symbol,
                                        name=name,
                                        balance=balance,
                                        contract_address=mint,
                                        decimals=int(token_amount["decimals"]),
                                        token_type=token_type
                                    )
                                    
                                    if token_type in ["staking", "liquidity", "lending"]:
                                        key = f"Unknown|{token_type}"
                                        if key not in defi_by_protocol:
                                            defi_by_protocol[key] = []
                                        defi_by_protocol[key].append(token)
                                    else:
                                        tokens.append(token)
                        except Exception:
                            continue
            
            # 创建 DeFi 仓位
            for key, tokens_list in defi_by_protocol.items():
                protocol, pos_type = key.split("|")
                defi_positions.append(DeFiPosition(
                    protocol=protocol,
                    position_type=pos_type,
                    tokens=tokens_list
                ))
        
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
        """获取 APT 和所有代币余额"""
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
                                                symbol=symbol,
                                                name=coin_type.split("::")[-1],
                                                balance=value / 1e8,
                                                contract_address=coin_type,
                                                decimals=8
                                            ))
                                except Exception:
                                    continue
            except Exception as e:
                print(f"APT API Error: {e}")
        
        return native_balance, tokens, defi_positions
    
    def _parse_coin_symbol(self, coin_type: str) -> str:
        """解析代币符号"""
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
        "ETH": "ethereum",
        "SOL": "solana",
        "APT": "aptos",
        "USDT": "tether",
        "USDC": "usd-coin",
        "DAI": "dai",
        "WBTC": "wrapped-bitcoin",
        "LINK": "chainlink",
        "UNI": "uniswap",
        "MATIC": "matic-network",
        "SHIB": "shiba-inu",
        "PEPE": "pepe",
        "WETH": "weth",
        "AAVE": "aave",
        "JUP": "jupiter-exchange-solana",
        "RAY": "raydium",
        "BONK": "bonk",
        "WIF": "dogwifcoin",
        "JTO": "jito-governance-token",
        "PYTH": "pyth-network",
        # Staking derivatives (价格接近原生代币)
        "stETH": "staked-ether",
        "wstETH": "wrapped-steth",
        "rETH": "rocket-pool-eth",
        "cbETH": "coinbase-wrapped-staked-eth",
        "frxETH": "frax-ether",
        "sfrxETH": "staked-frax-ether",
        "mSOL": "msol",
        "JitoSOL": "jito-staked-sol",
        "bSOL": "blazestake-staked-sol",
        "stSOL": "lido-staked-sol",
    }
    
    def __init__(self):
        self.prices: Dict[str, float] = {}
        self.last_update: Optional[datetime] = None
    
    async def update_prices(self) -> Dict[str, float]:
        """更新价格"""
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
        """获取价格"""
        if symbol.upper() in ["USDT", "USDC", "DAI", "BUSD", "TUSD"]:
            return 1.0
        return self.prices.get(symbol) or self.prices.get(symbol.upper())


class NotificationService:
    """通知服务"""
    
    def __init__(self, config: dict):
        self.config = config
    
    async def notify(self, message: str):
        """发送通知"""
        # Telegram
        tg = self.config.get("telegram", {})
        if tg.get("enabled"):
            try:
                url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json={
                        "chat_id": tg["chat_id"],
                        "text": message,
                        "parse_mode": "HTML"
                    })
            except Exception:
                pass
        
        # Discord
        dc = self.config.get("discord", {})
        if dc.get("enabled"):
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post(dc["webhook_url"], json={"content": message})
            except Exception:
                pass


class WalletMonitor:
    """钱包监控主类"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.monitors: Dict[str, ChainMonitor] = {}
        self.price_service = PriceService()
        self.notification_service = NotificationService(
            self.config.get("notifications", {})
        )
        self._init_monitors()
    
    def _load_config(self, config_path: str) -> dict:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _init_monitors(self):
        if "ethereum" in self.config:
            self.monitors["ethereum"] = EthereumMonitor(self.config["ethereum"])
        if "solana" in self.config:
            self.monitors["solana"] = SolanaMonitor(self.config["solana"])
        if "aptos" in self.config:
            self.monitors["aptos"] = AptosMonitor(self.config["aptos"])
    
    async def check_balance(self, chain: str, wallet: dict) -> Optional[WalletBalance]:
        """检查钱包余额"""
        monitor = self.monitors.get(chain)
        if not monitor:
            return None
        
        try:
            native_balance, tokens, defi_positions = await monitor.get_balance(wallet["address"])
            price = self.price_service.get_price(monitor.symbol)
            native_usd = native_balance * price if price else None
            
            # 计算代币和 DeFi 仓位的 USD 价值
            for token in tokens:
                token_price = self.price_service.get_price(token.symbol)
                if token_price:
                    token.usd_value = token.balance * token_price
            
            for position in defi_positions:
                total = 0.0
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
        """检查所有钱包"""
        tasks = []
        for chain in self.monitors:
            wallets = self.config.get(chain, {}).get("wallets", [])
            for wallet in wallets:
                tasks.append(self.check_balance(chain, wallet))
        
        balances = await asyncio.gather(*tasks)
        return [b for b in balances if b is not None]
    
    def _format_number(self, num: float) -> str:
        """格式化数字"""
        if num >= 1_000_000:
            return f"{num:,.0f}"
        elif num >= 1:
            return f"{num:,.4f}"
        else:
            return f"{num:,.6f}"
    
    def _format_balance(self, balance: WalletBalance) -> str:
        """格式化输出"""
        lines = []
        
        # 钱包标题
        lines.append(f"\n  📍 [{balance.chain}] {balance.name}")
        
        # 原生代币
        usd = f" (${balance.native_usd_value:,.2f})" if balance.native_usd_value else ""
        lines.append(f"     ├─ 💰 {self._format_number(balance.native_balance)} {balance.native_symbol}{usd}")
        
        # 普通代币
        if balance.tokens:
            lines.append(f"     │")
            lines.append(f"     ├─ 🪙 代币:")
            sorted_tokens = sorted(balance.tokens, key=lambda t: t.usd_value or 0, reverse=True)
            for token in sorted_tokens[:20]:  # 只显示前20个
                usd = f" (${token.usd_value:,.2f})" if token.usd_value else ""
                lines.append(f"     │  └─ {self._format_number(token.balance)} {token.symbol}{usd}")
            if len(balance.tokens) > 20:
                lines.append(f"     │  └─ ... 还有 {len(balance.tokens) - 20} 个代币")
        
        # DeFi 仓位
        if balance.defi_positions:
            lines.append(f"     │")
            lines.append(f"     └─ 🏦 DeFi 仓位:")
            for pos in balance.defi_positions:
                type_emoji = {
                    "staking": "🥩",
                    "lending": "🏛️",
                    "liquidity": "💧",
                    "farming": "🌾"
                }.get(pos.position_type, "📊")
                
                usd = f" (${pos.total_usd_value:,.2f})" if pos.total_usd_value else ""
                lines.append(f"        ├─ {type_emoji} {pos.protocol} [{pos.position_type}]{usd}")
                for token in pos.tokens:
                    t_usd = f" (${token.usd_value:,.2f})" if token.usd_value else ""
                    lines.append(f"        │  └─ {self._format_number(token.balance)} {token.symbol}{t_usd}")
        
        return "\n".join(lines)
    
    async def run_once(self) -> List[WalletBalance]:
        """运行一次检查"""
        print(f"\n{'='*70}")
        print(f"⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        print("📈 获取代币价格...")
        await self.price_service.update_prices()
        
        print("🔍 查询钱包余额 (包括 DeFi 仓位)...\n")
        balances = await self.check_all_balances()
        
        total_usd = 0.0
        total_defi = 0.0
        
        for balance in balances:
            print(self._format_balance(balance))
            
            if balance.native_usd_value:
                total_usd += balance.native_usd_value
            for token in balance.tokens:
                if token.usd_value:
                    total_usd += token.usd_value
            for pos in balance.defi_positions:
                if pos.total_usd_value:
                    total_usd += pos.total_usd_value
                    total_defi += pos.total_usd_value
        
        print(f"\n{'─'*70}")
        print(f"💰 总资产价值: ${total_usd:,.2f} USD")
        if total_defi > 0:
            print(f"🏦 其中 DeFi 仓位: ${total_defi:,.2f} USD")
        print(f"{'='*70}")
        
        return balances
    
    async def run(self):
        """持续运行"""
        interval = self.config.get("monitor_interval", 60)
        print("🚀 钱包余额监控启动 (含 DeFi 仓位)")
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
    parser = argparse.ArgumentParser(description="多链钱包监控 (含 DeFi)")
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
