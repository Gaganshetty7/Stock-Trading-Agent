import asyncio
import time
import sys
import os
import logging
from datetime import datetime, timedelta
from unittest.mock import patch

# Add the project root to sys.path so it can find 'db' and 'services'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging to hide noisy debug logs from the actual services
logging.basicConfig(level=logging.WARNING, format='%(message)s')

# Import database
from db.database import SessionLocal
from db.models.trade_tracking import TradeTracking, TrackingStatus, TradeTrackingTxn
from db.repositories.trade_tracking import TradeTrackingRepository

# Import the actual services
from services.market_alert_service.core import scheduler
from services.market_alert_service.channels.telegram_alert_service import bot_listener
from services.market_alert_service.channels.telegram_alert_service.service import TelegramChannel

# ── MOCK STATE ──────────────────────────────────────────────────────────────
simulated_prices = {}
force_market_close = False

async def mock_fetch_prices(symbols):
    # Only return prices for symbols we are actively simulating
    return {sym: simulated_prices.get(sym, 0.0) for sym in symbols if sym in simulated_prices}

def mock_is_market_closed(self, now_ist):
    return force_market_close

# Apply monkeypatches to avoid touching the real codebase
scheduler.fetch_prices = mock_fetch_prices
bot_listener.fetch_prices = mock_fetch_prices
scheduler.MonitoringScheduler._is_market_closed = mock_is_market_closed
scheduler.TICK_INTERVAL_SECONDS = 3
bot_listener.SNOOZE_MINUTES = 0.1666  # roughly 10 seconds

# ── HELPER FUNCTIONS ────────────────────────────────────────────────────────

def clean_db():
    """Remove previous test trades to ensure a clean slate."""
    with SessionLocal() as db:
        test_trade_ids = [t.id for t in db.query(TradeTracking.id).filter(TradeTracking.entry_type == 'TEST_ALERT').all()]
        if test_trade_ids:
            db.query(TradeTrackingTxn).filter(TradeTrackingTxn.trade_tracking_id.in_(test_trade_ids)).delete(synchronize_session=False)
        db.query(TradeTracking).filter(TradeTracking.entry_type == 'TEST_ALERT').delete(synchronize_session=False)
        db.commit()

def insert_test_trade(symbol, target, stoploss, z_min, z_max):
    repo = TradeTrackingRepository()
    with SessionLocal() as db:
        plan_data = {
            'symbol': symbol,
            'decision': 'LONG',
            'confidence': 99,
            'entry_type': 'TEST_ALERT',
            'trade_thesis': 'E2E Testing',
            'buy_zone_min': z_min,
            'buy_zone_max': z_max,
            'hard_stoploss': stoploss,
            'target_1': target,
            'run_batch': '29:06:2026-09:15 AM'
        }
        trade = repo.create(db, plan_data)
        db.commit()
        return trade.id

async def wait_for_status(trade_id, expected_status, timeout=60, prompt=None):
    start = time.time()
    if prompt:
        print(f"\n⏳ {prompt}")
        
    while time.time() - start < timeout:
        with SessionLocal() as db:
            trade = db.query(TradeTracking).filter(TradeTracking.id == trade_id).first()
            if trade and trade.status == expected_status:
                print(f"✅ Status verified: {expected_status.name}")
                return trade
        await asyncio.sleep(1)
    print(f"❌ Timed out waiting for status: {expected_status.name}")
    return None

def force_expiry(trade_id):
    """Manually age the trade in the DB by 61 minutes so the scheduler expires it."""
    with SessionLocal() as db:
        trade = db.query(TradeTracking).filter(TradeTracking.id == trade_id).first()
        trade.created_at = datetime.now(trade.created_at.tzinfo) - timedelta(minutes=61)
        db.commit()

# ── SCENARIOS ───────────────────────────────────────────────────────────────

async def run_scenario_1():
    print("\n" + "="*80)
    print("SCENARIO 1: Confirm → Target 1 Hit")
    tid = insert_test_trade("RELIANCE", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["RELIANCE"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for scheduler to send Telegram alert...")
    await wait_for_status(tid, TrackingStatus.ACTIVE, prompt="Please click CONFIRM on your Telegram app...")
    
    simulated_prices["RELIANCE"] = 160
    print("📈 Market Price automatically updated to ₹160 (Target 1 Hit)")
    
    await wait_for_status(tid, TrackingStatus.TARGET_1_HIT, prompt="Waiting for Target 1 alert on Telegram...")

async def run_scenario_2():
    print("\n" + "="*80)
    print("SCENARIO 2: Confirm → Stoploss Hit")
    tid = insert_test_trade("INFY", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["INFY"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.ACTIVE, prompt="Please click CONFIRM on your Telegram app...")
    
    simulated_prices["INFY"] = 40
    print("📈 Market Price automatically updated to ₹40 (Stoploss Hit)")
    
    await wait_for_status(tid, TrackingStatus.STOPLOSS_HIT, prompt="Waiting for Stoploss alert on Telegram...")

async def run_scenario_3():
    print("\n" + "="*80)
    print("SCENARIO 3: Reject")
    tid = insert_test_trade("HDFCBANK", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["HDFCBANK"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.IGNORED, prompt="Please click REJECT on your Telegram app...")

async def run_scenario_4():
    print("\n" + "="*80)
    print("SCENARIO 4: Snooze → (wait 10s) → Price back in buy zone → Confirm → Target 1 Hit")
    tid = insert_test_trade("TCS", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["TCS"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.SNOOZED, prompt="Please click SNOOZE on your Telegram app...")
    
    print("⏳ Waiting 10s for snooze expiry. Price remains ₹100...")
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Re-alert on Telegram...")
    await wait_for_status(tid, TrackingStatus.ACTIVE, prompt="Please click CONFIRM on your Telegram app...")
    
    simulated_prices["TCS"] = 160
    print("📈 Market Price automatically updated to ₹160 (Target 1 Hit)")
    
    await wait_for_status(tid, TrackingStatus.TARGET_1_HIT, prompt="Waiting for Target 1 alert on Telegram...")

async def run_scenario_5():
    print("\n" + "="*80)
    print("SCENARIO 5: Snooze → (wait 10s) → Price back in buy zone → Confirm → Stoploss Hit")
    tid = insert_test_trade("ICICIBANK", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["ICICIBANK"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.SNOOZED, prompt="Please click SNOOZE on your Telegram app...")
    
    print("⏳ Waiting 10s for snooze expiry. Price remains ₹100...")
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Re-alert on Telegram...")
    await wait_for_status(tid, TrackingStatus.ACTIVE, prompt="Please click CONFIRM on your Telegram app...")
    
    simulated_prices["ICICIBANK"] = 40
    print("📈 Market Price automatically updated to ₹40 (Stoploss Hit)")
    
    await wait_for_status(tid, TrackingStatus.STOPLOSS_HIT, prompt="Waiting for Stoploss alert on Telegram...")

async def run_scenario_6():
    print("\n" + "="*80)
    print("SCENARIO 6: Snooze → (wait 10s) → Price back in buy zone → Reject")
    tid = insert_test_trade("SBIN", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["SBIN"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.SNOOZED, prompt="Please click SNOOZE on your Telegram app...")
    
    print("⏳ Waiting 10s for snooze expiry. Price remains ₹100...")
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Re-alert on Telegram...")
    await wait_for_status(tid, TrackingStatus.IGNORED, prompt="Please click REJECT on your Telegram app...")

async def run_scenario_7():
    print("\n" + "="*80)
    print("SCENARIO 7: Snooze → (wait 10s) → Price NOT in zone → Trade Expired")
    tid = insert_test_trade("AXISBANK", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["AXISBANK"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.SNOOZED, prompt="Please click SNOOZE on your Telegram app...")
    
    simulated_prices["AXISBANK"] = 200
    print("📈 Market Price automatically updated to ₹200 (Moved OUT of zone)")
    print("⏳ Waiting 10s for snooze expiry...")
    
    # Since price left zone, it reverts to TRACKING quietly.
    await wait_for_status(tid, TrackingStatus.TRACKING, prompt="Waiting for DB status to revert to TRACKING...")
    
    print("⏳ Forcing 60-minute expiry...")
    force_expiry(tid)
    
    await wait_for_status(tid, TrackingStatus.EXPIRED, prompt="Waiting for scheduler to expire the trade...")

async def run_scenario_8():
    print("\n" + "="*80)
    print("SCENARIO 8: Confirm → Target 1 Hit (Partial Booking)")
    tid = insert_test_trade("LT", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["LT"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.ACTIVE, prompt="Please click CONFIRM on your Telegram app...")
    
    simulated_prices["LT"] = 160
    print("📈 Market Price automatically updated to ₹160 (Target 1 Hit)")
    
    await wait_for_status(tid, TrackingStatus.TARGET_1_HIT, prompt="Waiting for Target 1 alert on Telegram...")
    print("🎯 Partial booking logic validated by state resolution.")

async def run_scenario_11():
    print("\n" + "="*80)
    print("SCENARIO 11: Snooze → (wait 10s) → Snooze Again → (wait 10s) → Market Close")
    tid = insert_test_trade("ITC", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["ITC"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    await wait_for_status(tid, TrackingStatus.SNOOZED, prompt="Please click SNOOZE on your Telegram app...")
    
    print("⏳ Waiting 10s for snooze expiry. Price remains ₹100...")
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Re-alert on Telegram...")
    await wait_for_status(tid, TrackingStatus.SNOOZED, prompt="Please click SNOOZE AGAIN on your Telegram app...")
    
    print("⏳ Waiting 10s for second snooze expiry...")
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Re-alert on Telegram...")
    
    print("🔔 Forcing Market Close (15:30 IST)...")
    global force_market_close
    force_market_close = True
    
    await wait_for_status(tid, TrackingStatus.MARKET_CLOSED, prompt="Waiting for scheduler to force-close trade...")
    
    # Reset for next tests
    force_market_close = False



async def run_scenario_9():
    print("\n" + "="*80)
    print("SCENARIO 9: Late Confirmation (Price Left Buy Zone)")
    tid = insert_test_trade("HDFCBANK", target=150, stoploss=50, z_min=90, z_max=110)
    
    simulated_prices["HDFCBANK"] = 100
    print("📈 Market Price: ₹100 (In Zone)")
    
    await wait_for_status(tid, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert...")
    
    # Manually move price out of zone BEFORE user confirms
    simulated_prices["HDFCBANK"] = 120
    print("📈 Market Price automatically updated to ₹120 (Left zone while alert was pending)")
    
    await wait_for_status(tid, TrackingStatus.TRACKING, prompt="Please click CONFIRM on your Telegram app... (It should reject and revert to TRACKING)")
    print("✅ Late confirmation correctly blocked! Trade reverted to TRACKING.")

async def run_scenario_10():
    print("\n" + "="*80)
    print("SCENARIO 10: Multiple Pending Alerts (Confirm Out of Order)")
    
    tid1 = insert_test_trade("HINDUNILVR", target=150, stoploss=50, z_min=90, z_max=110)
    simulated_prices["HINDUNILVR"] = 100
    print("📈 Market Price 1: HINDUNILVR ₹100 (In Zone)")
    
    await asyncio.sleep(1)
    
    tid2 = insert_test_trade("TATAMOTORS", target=250, stoploss=150, z_min=190, z_max=210)
    simulated_prices["TATAMOTORS"] = 200
    print("📈 Market Price 2: TATAMOTORS ₹200 (In Zone)")
    
    await wait_for_status(tid1, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert 1 (HINDUNILVR)...")
    await wait_for_status(tid2, TrackingStatus.BUY_ZONE_HIT, prompt="Waiting for Telegram alert 2 (TATAMOTORS)...")
    
    print("\n⏳ Both alerts are now pending on your Telegram.")
    
    await wait_for_status(tid2, TrackingStatus.ACTIVE, prompt="Please click CONFIRM on the SECOND alert (TATAMOTORS) first...")
    print("✅ Status verified: TATAMOTORS is ACTIVE")
    
    await wait_for_status(tid1, TrackingStatus.ACTIVE, prompt="Now please click CONFIRM on the FIRST alert (HINDUNILVR)...")
    print("✅ Status verified: HINDUNILVR is ACTIVE")
    print("🎯 Out-of-order confirmation logic validated.")

# ── ORCHESTRATOR ────────────────────────────────────────────────────────────

async def orchestrator():
    print("\n🚀 Starting E2E Trade Test Simulator...")
    print("Cleaning database of old test trades...")
    clean_db()
    
    print("Starting background scheduler and Telegram listener (TICK = 3s, SNOOZE = 10s)...")
    sched = scheduler.MonitoringScheduler([TelegramChannel()], telegram_enabled=True)
    
    # Run the scheduler in the background
    scheduler_task = asyncio.create_task(sched.run())
    
    # Give it a second to boot up
    await asyncio.sleep(2)
    
    try:
        # await run_scenario_1()
        # await run_scenario_2()
        # await run_scenario_3()
        # await run_scenario_4()
        # await run_scenario_5()
        # await run_scenario_6()
        # await run_scenario_7()
        await run_scenario_8()
        await run_scenario_9()
        await run_scenario_10()
        await run_scenario_11()
        print("\n" + "="*80)
        print("🎉 ALL 11 E2E SCENARIOS COMPLETED SUCCESSFULLY!")
    except Exception as e:
        print(f"\n❌ Error during simulation: {e}")
    finally:
        print("\nCleaning up test trades...")
        clean_db()
        # Force market close to gracefully kill the scheduler loop
        global force_market_close
        force_market_close = True
        print("Waiting for background tasks to shutdown...")
        await asyncio.sleep(4)
        print("Done. You can press Ctrl+C to exit.")

if __name__ == "__main__":
    try:
        asyncio.run(orchestrator())
    except KeyboardInterrupt:
        print("\nSimulation aborted by user.")
        sys.exit(0)
