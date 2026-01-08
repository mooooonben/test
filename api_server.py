#!/usr/bin/env python3
"""
钱包监控 API 服务器
提供 RESTful API 和 Web 仪表盘
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# 导入钱包监控模块
from wallet_monitor import WalletMonitor, WalletBalance, DeFiPosition, TokenBalance


# ========== 数据模型 ==========

class TokenBalanceResponse(BaseModel):
    symbol: str
    name: str
    balance: float
    usd_value: Optional[float] = None
    token_type: str = "token"

class DeFiPositionResponse(BaseModel):
    protocol: str
    position_type: str
    tokens: List[TokenBalanceResponse]
    total_usd_value: Optional[float] = None
    # 借贷详情
    supplied: Optional[List[TokenBalanceResponse]] = None
    borrowed: Optional[List[TokenBalanceResponse]] = None
    health_factor: Optional[float] = None
    net_worth_usd: Optional[float] = None

class WalletResponse(BaseModel):
    chain: str
    address: str
    name: str
    native_balance: float
    native_symbol: str
    native_usd_value: Optional[float] = None
    tokens: List[TokenBalanceResponse]
    defi_positions: List[DeFiPositionResponse]
    timestamp: str

class DashboardSummary(BaseModel):
    total_usd_value: float
    total_defi_value: float
    total_debt_value: float
    net_worth: float
    chains: Dict[str, float]
    last_updated: str

class HistoryPoint(BaseModel):
    timestamp: str
    total_usd: float


# ========== 数据库 ==========

DB_PATH = Path("wallet_history.db")

def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 创建历史记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            total_usd REAL NOT NULL,
            defi_usd REAL DEFAULT 0,
            debt_usd REAL DEFAULT 0,
            data_json TEXT
        )
    """)
    
    # 创建钱包快照表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallet_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            balance_json TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def save_history(total_usd: float, defi_usd: float, debt_usd: float, data: dict):
    """保存历史记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO balance_history (timestamp, total_usd, defi_usd, debt_usd, data_json)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), total_usd, defi_usd, debt_usd, json.dumps(data)))
    
    conn.commit()
    conn.close()

def get_history(days: int = 7) -> List[dict]:
    """获取历史记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    cursor.execute("""
        SELECT timestamp, total_usd, defi_usd, debt_usd
        FROM balance_history
        WHERE timestamp > ?
        ORDER BY timestamp ASC
    """, (since,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {"timestamp": row[0], "total_usd": row[1], "defi_usd": row[2], "debt_usd": row[3]}
        for row in rows
    ]


# ========== 全局状态 ==========

class AppState:
    def __init__(self):
        self.monitor: Optional[WalletMonitor] = None
        self.last_balances: List[WalletBalance] = []
        self.last_update: Optional[datetime] = None
        self.is_updating: bool = False
        self.summary: Optional[DashboardSummary] = None

state = AppState()


# ========== FastAPI 应用 ==========

async def background_scheduler():
    """后台定时更新任务"""
    while True:
        try:
            # 等待配置的间隔时间
            interval = 300  # 默认 5 分钟
            if state.monitor and state.monitor.config:
                interval = state.monitor.config.get("monitor_interval", 300)
            
            await asyncio.sleep(interval)
            
            # 执行更新
            if state.monitor and not state.is_updating:
                print(f"⏰ 定时更新触发 (间隔: {interval}秒)")
                await update_balances()
                
        except Exception as e:
            print(f"❌ 后台更新出错: {e}")
            await asyncio.sleep(60)  # 出错后等待 1 分钟再试


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    init_db()
    try:
        state.monitor = WalletMonitor("config.yaml")
        print("✅ 钱包监控器初始化成功")
        
        # 启动时立即更新一次
        asyncio.create_task(update_balances())
        
        # 启动后台定时任务
        scheduler_task = asyncio.create_task(background_scheduler())
        print("⏰ 后台定时更新已启动")
        
    except FileNotFoundError:
        print("⚠️ config.yaml 不存在，请先创建配置文件")
        scheduler_task = None
    
    yield
    
    # 关闭时清理
    if scheduler_task:
        scheduler_task.cancel()
    print("👋 服务器关闭")


app = FastAPI(
    title="钱包监控仪表盘",
    description="多链钱包余额监控 API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")


# ========== 辅助函数 ==========

def convert_token(token: TokenBalance) -> TokenBalanceResponse:
    """转换代币对象"""
    return TokenBalanceResponse(
        symbol=token.symbol,
        name=token.name,
        balance=token.balance,
        usd_value=token.usd_value,
        token_type=token.token_type
    )

def convert_position(pos: DeFiPosition) -> DeFiPositionResponse:
    """转换 DeFi 仓位对象"""
    response = DeFiPositionResponse(
        protocol=pos.protocol,
        position_type=pos.position_type,
        tokens=[convert_token(t) for t in pos.tokens],
        total_usd_value=pos.total_usd_value
    )
    
    # 借贷详情
    if pos.lending_details:
        ld = pos.lending_details
        response.supplied = [convert_token(t) for t in ld.supplied]
        response.borrowed = [convert_token(t) for t in ld.borrowed]
        response.health_factor = ld.health_factor
        response.net_worth_usd = ld.net_worth_usd
    
    return response

def convert_wallet(wallet: WalletBalance) -> WalletResponse:
    """转换钱包对象"""
    return WalletResponse(
        chain=wallet.chain,
        address=wallet.address,
        name=wallet.name,
        native_balance=wallet.native_balance,
        native_symbol=wallet.native_symbol,
        native_usd_value=wallet.native_usd_value,
        tokens=[convert_token(t) for t in wallet.tokens],
        defi_positions=[convert_position(p) for p in wallet.defi_positions],
        timestamp=wallet.timestamp.isoformat()
    )

def calculate_summary(balances: List[WalletBalance]) -> DashboardSummary:
    """计算汇总数据"""
    total_usd = 0.0
    total_defi = 0.0
    total_debt = 0.0
    chains: Dict[str, float] = {}
    
    for balance in balances:
        chain_total = 0.0
        
        # 原生代币
        if balance.native_usd_value:
            chain_total += balance.native_usd_value
        
        # 代币
        for token in balance.tokens:
            if token.usd_value:
                chain_total += token.usd_value
        
        # DeFi 仓位
        for pos in balance.defi_positions:
            if pos.lending_details:
                chain_total += pos.lending_details.net_worth_usd
                total_defi += pos.lending_details.total_supplied_usd
                total_debt += pos.lending_details.total_borrowed_usd
            elif pos.total_usd_value:
                chain_total += pos.total_usd_value
                total_defi += pos.total_usd_value
        
        total_usd += chain_total
        chains[balance.chain] = chains.get(balance.chain, 0) + chain_total
    
    return DashboardSummary(
        total_usd_value=total_usd,
        total_defi_value=total_defi,
        total_debt_value=total_debt,
        net_worth=total_usd,
        chains=chains,
        last_updated=datetime.now().isoformat()
    )


# ========== API 路由 ==========

@app.get("/", response_class=HTMLResponse)
async def root():
    """返回仪表盘页面"""
    index_path = Path("static/index.html")
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>钱包监控仪表盘</h1><p>请先创建 static/index.html</p>")


@app.get("/api/summary", response_model=DashboardSummary)
async def get_summary():
    """获取资产汇总"""
    if state.summary is None:
        raise HTTPException(status_code=404, detail="暂无数据，请先刷新")
    return state.summary


@app.get("/api/wallets", response_model=List[WalletResponse])
async def get_wallets():
    """获取所有钱包余额"""
    if not state.last_balances:
        raise HTTPException(status_code=404, detail="暂无数据，请先刷新")
    return [convert_wallet(w) for w in state.last_balances]


@app.get("/api/wallet/{chain}/{address}", response_model=WalletResponse)
async def get_wallet(chain: str, address: str):
    """获取单个钱包余额"""
    for wallet in state.last_balances:
        if wallet.chain.lower() == chain.lower() and wallet.address.lower() == address.lower():
            return convert_wallet(wallet)
    raise HTTPException(status_code=404, detail="钱包未找到")


@app.get("/api/history")
async def get_balance_history(days: int = 7):
    """获取历史余额"""
    return get_history(days)


@app.post("/api/refresh")
async def refresh_balances(background_tasks: BackgroundTasks):
    """刷新所有余额"""
    if state.monitor is None:
        raise HTTPException(status_code=500, detail="监控器未初始化")
    
    if state.is_updating:
        return {"status": "already_updating", "message": "正在更新中..."}
    
    background_tasks.add_task(update_balances)
    return {"status": "started", "message": "开始更新余额..."}


async def update_balances():
    """后台更新余额"""
    if state.monitor is None or state.is_updating:
        return
    
    state.is_updating = True
    
    try:
        print("🔄 开始更新余额...")
        
        # 更新价格
        await state.monitor.price_service.update_prices()
        
        # 获取余额
        balances = await state.monitor.check_all_balances()
        
        state.last_balances = balances
        state.last_update = datetime.now()
        state.summary = calculate_summary(balances)
        
        # 保存历史
        save_history(
            state.summary.total_usd_value,
            state.summary.total_defi_value,
            state.summary.total_debt_value,
            {"chains": state.summary.chains}
        )
        
        print(f"✅ 更新完成，总资产: ${state.summary.total_usd_value:,.2f}")
        
    except Exception as e:
        print(f"❌ 更新失败: {e}")
    
    finally:
        state.is_updating = False


@app.get("/api/status")
async def get_status():
    """获取系统状态"""
    return {
        "is_updating": state.is_updating,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "wallet_count": len(state.last_balances),
        "chains": list(state.monitor.monitors.keys()) if state.monitor else []
    }


# ========== 启动 ==========

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
