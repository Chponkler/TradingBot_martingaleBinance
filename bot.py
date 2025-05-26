import os
import time
import decimal
from binance import Client
from binance.exceptions import BinanceAPIException

# Настройки
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
SYMBOL = 'XRPUSDT'
COMMISSION = decimal.Decimal('0.001')  # 0.1% комиссия Binance

# Параметры стратегии
START_PRICE = decimal.Decimal('2.315')
DECLINE_PERCENT = decimal.Decimal('0.5')
INITIAL_AMOUNT = decimal.Decimal('0.5')
MULTIPLIER = decimal.Decimal('1.4')
MAX_STEPS = 10
PROFIT_PERCENT = decimal.Decimal('2')

client = Client(API_KEY, API_SECRET, testnet=True)

class TradingBot:
    def __init__(self):
        self.entry_price = None
        self.current_step = 0
        self.total_quantity = decimal.Decimal('0')
        self.total_spent = decimal.Decimal('0')
        self.next_buy_amount = INITIAL_AMOUNT
        self.required_balance = self.calculate_required_balance()
        self.active_orders = []

    def calculate_required_balance(self):
        """Рассчитывает необходимый баланс с учетом комиссий"""
        total = decimal.Decimal('0')
        current_amount = INITIAL_AMOUNT

        for _ in range(MAX_STEPS):
            total += current_amount * (1 + COMMISSION)
            current_amount *= MULTIPLIER

        return total.quantize(decimal.Decimal('0.00'))

    def get_usdt_balance(self):
        """Получаем текущий баланс USDT"""
        try:
            balance = client.get_asset_balance(asset='USDT')
            return decimal.Decimal(balance['free'])
        except BinanceAPIException as e:
            print(f"❌ Ошибка получения баланса: {e.message}")
            return decimal.Decimal('0')

    def confirm_start(self):
        """Подтверждение запуска с проверкой баланса"""
        print("\n" + "="*50)
        print(f"📊 Параметры стратегии:")
        print(f"• Цена активации: {START_PRICE} USDT")
        print(f"• Шагов DCA: {MAX_STEPS}")
        print(f"• Начальная сумма: {INITIAL_AMOUNT} USDT")
        print(f"• Множитель шага: {MULTIPLIER}")
        print(f"• Цель прибыли: {PROFIT_PERCENT}%")
        print(f"• Требуемый баланс: {self.required_balance} USDT (с комиссией {COMMISSION*100}%)")

        balance = self.get_usdt_balance()
        print(f"\n💰 Ваш текущий баланс: {balance} USDT")

        if balance < self.required_balance:
            print("\n⚠️ Внимание: Недостаточно средств!")
            print(f"Необходимо пополнить баланс минимум на {self.required_balance - balance:.2f} USDT")

        choice = input("\nЗапустить бота? (yes/no): ").strip().lower()
        if choice != 'yes':
            print("Отмена запуска...")
            exit()
        print("="*50 + "\n")

    def get_current_price(self):
        """Текущая цена XRP"""
        try:
            ticker = client.get_symbol_ticker(symbol=SYMBOL)
            return decimal.Decimal(ticker['price'])
        except BinanceAPIException as e:
            print(f"❌ Ошибка получения цены: {e.message}")
            return None

    def wait_for_start_price(self):
        """Ожидание стартовой цены"""
        print(f"🕒 Ожидаем цену активации {START_PRICE} USDT")
        while True:
            price = self.get_current_price()
            print(f" Текущая цена {price} USDT")
            if True:     #price and price == START_PRICE:
                print(f"✅ Цена достигла {price}, активируем бота!")
                self.entry_price = price
                return
            time.sleep(1)

    def calculate_target_price(self, step):
        """Цена для срабатывания ступени"""
        return self.entry_price * (1 - DECLINE_PERCENT/100 * (step + 1))

    def buy_xrp(self, amount):
        """Покупка XRP на указанную сумму"""
        try:
            price = self.get_current_price()
            if not price:
                return False

            print(f"\n🛒 Покупаем {amount} USDT XRP по цене {price:.4f}")
            quantity = round(amount / price, 4)

            # Рассчитываем комиссию
            commission = quantity * COMMISSION
            total_quantity = quantity - commission

            order = client.create_order(
                symbol=SYMBOL,
                side=Client.SIDE_BUY,
                type=Client.ORDER_TYPE_MARKET,
                quantity=quantity
            )

            executed_qty = decimal.Decimal(order['executedQty'])
            self.total_quantity += executed_qty - commission
            self.total_spent += amount

            print(f"✅ Куплено {executed_qty:.2f} XRP за {amount:.2f} USDT")
            print(f"💸 Удержано комиссии: {commission:.4f} XRP")
            return True

        except BinanceAPIException as e:
            print(f"❌ Ошибка покупки: {e.message}")
            return False

    def sell_all_xrp(self):
        """Продажа всего XRP"""
        try:
            balance = client.get_asset_balance(asset='XRP')
            free = decimal.Decimal(balance['free'])
            if free <= decimal.Decimal('0.0001'):
                return

            print(f"\n💰 Продаем {free:.2f} XRP...")
            order = client.create_order(
                symbol=SYMBOL,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=free
            )

            # Рассчитываем комиссию
            executed_qty = decimal.Decimal(order['executedQty'])
            commission = executed_qty * COMMISSION
            received = executed_qty - commission

            print(f"✅ Продано {received:.2f} USDT")
            print(f"💸 Удержано комиссии: {commission:.4f} XRP")
            self.reset()

        except BinanceAPIException as e:
            print(f"❌ Ошибка продажи: {e.message}")

    def check_profit_condition(self):
        """Проверка условия для фиксации прибыли"""
        if self.total_quantity == 0:
            return False

        avg_price = self.total_spent / self.total_quantity
        current_price = self.get_current_price()
        if not current_price:
            return False

        target_price = avg_price * (1 + PROFIT_PERCENT/100)
        return current_price >= target_price

    def reset(self):
        """Сброс состояния бота"""
        self.__init__()
        print("\n♻️ Состояние бота сброшено")

    def run(self):
        self.confirm_start()
        self.wait_for_start_price()

        while self.current_step < MAX_STEPS:
            current_price = self.get_current_price()
            if not current_price:
                time.sleep(3)
                continue

            target_price = self.calculate_target_price(self.current_step)

            print(f"\nШаг {self.current_step + 1}/{MAX_STEPS}")
            print(f"Текущая цена: {current_price:.4f}")
            print(f"Целевая цена покупки: {target_price:.4f}")
            print(f"Сумма покупки: {self.next_buy_amount:.2f} USDT")
            print(f"Потрачено всего: {self.total_spent:.2f} USDT")
            print(f"Накоплено XRP: {self.total_quantity:.2f}")

            if current_price <= target_price:
                if self.buy_xrp(self.next_buy_amount):
                    self.next_buy_amount *= MULTIPLIER
                    self.current_step += 1

                    if self.check_profit_condition():
                        print(f"\n🎯 Условие прибыли достигнуто!")
                        self.sell_all_xrp()
                        return

            time.sleep(3)

        print("\n⚠️ Достигнут максимум шагов. Ожидаем условия для продажи...")
        while True:
            if self.check_profit_condition():
                self.sell_all_xrp()
                break
            time.sleep(3)

if __name__ == "__main__":
    bot = TradingBot()
    while True:
        try:
            bot.run()
            print("\n🔄 Перезапуск бота...")
            time.sleep(5)
        except KeyboardInterrupt:
            choice = input("Продать все позиции перед выходом? (yes/no): ")
            if choice.lower() == 'yes':
                bot.sell_all_xrp()
                break
            else:
                break
