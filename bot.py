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
START_PRICE = decimal.Decimal('2.2857')  # Цена активации бота
DECLINE_PERCENT = decimal.Decimal('0.2')  # Процент падения для следующей покупки (например, 5% от entry_price)
INITIAL_AMOUNT = decimal.Decimal('10')  # Начальная сумма покупки в USDT (увеличена до 10 для соответствия MIN_NOTIONAL)
MULTIPLIER = decimal.Decimal('1.3')  # Множитель для увеличения суммы покупки на каждом шаге
MAX_STEPS = 10  # Максимальное количество шагов усреднения (после начальной покупки)
PROFIT_PERCENT = decimal.Decimal('0.5')  # Процент прибыли для продажи от средней цены

# Инициализация клиента Binance (используем тестовую сеть для безопасного тестирования)
client = Client(API_KEY, API_SECRET, testnet=True)

class TradingBot:
    def __init__(self):
        # Переменные состояния бота
        self.entry_price = None  # Цена, по которой алгоритм был активирован (START_PRICE или ниже)
        self.current_step = 0  # Текущий шаг усреднения (0 для первого шага DCA, 1 для второго и т.д.)
        self.total_quantity = decimal.Decimal('0')  # Общее количество купленных XRP
        self.total_spent = decimal.Decimal('0')  # Общая сумма потраченных USDT
        self.next_buy_amount = INITIAL_AMOUNT  # Сумма для следующей покупки
        self.symbol_info = self._get_symbol_info() # Информация о торговой паре (минимальные значения, точность)

        # Проверка, что информация о символе получена
        if not self.symbol_info:
            print("❌ Не удалось получить информацию о символе. Проверьте SYMBOL или подключение к API.")
            exit()

        self.required_balance = self._calculate_required_balance()
        self.active_orders = [] # Для отслеживания активных ордеров, если бы использовались лимитные ордера

    def _get_symbol_info(self):
        """Получает информацию о торговой паре (XRPUSDT) с Binance."""
        try:
            exchange_info = client.get_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == SYMBOL:
                    info = {
                        'minQty': decimal.Decimal('0'),
                        'stepSize': decimal.Decimal('0'),
                        'minNotional': decimal.Decimal('0')
                    }
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            info['minQty'] = decimal.Decimal(f['minQty'])
                            info['stepSize'] = decimal.Decimal(f['stepSize'])
                        elif f['filterType'] == 'MIN_NOTIONAL':
                            info['minNotional'] = decimal.Decimal(f['minNotional'])
                    return info
            return None
        except BinanceAPIException as e:
            print(f"❌ Ошибка получения информации о символе: {e.message}")
            return None

    def _quantize_quantity(self, quantity):
        """Округляет количество до ближайшего шага, разрешенного Binance."""
        if not self.symbol_info:
            return quantity # Возвращаем исходное, если инфо нет (будет ошибка позже)
        step_size = self.symbol_info['stepSize']
        # Используем quantize для округления к ближайшему шагу
        return (quantity / step_size).quantize(decimal.Decimal('1.'), rounding=decimal.ROUND_DOWN) * step_size

    def _calculate_required_balance(self):
        """Рассчитывает необходимый баланс USDT для выполнения всех шагов с учетом комиссий."""
        total = INITIAL_AMOUNT * (1 + COMMISSION) # Начальная покупка
        current_amount = INITIAL_AMOUNT

        for _ in range(MAX_STEPS): # Добавляем MAX_STEPS DCA покупок
            current_amount *= MULTIPLIER
            total += current_amount * (1 + COMMISSION)

        # Округляем до двух знаков после запятой
        return total.quantize(decimal.Decimal('0.00'))

    def get_usdt_balance(self):
        """Получает текущий баланс USDT."""
        try:
            balance = client.get_asset_balance(asset='USDT')
            return decimal.Decimal(balance['free'])
        except BinanceAPIException as e:
            print(f"❌ Ошибка получения баланса USDT: {e.message}")
            return decimal.Decimal('0')

    def get_xrp_balance(self):
        """Получает текущий баланс XRP."""
        try:
            balance = client.get_asset_balance(asset='XRP')
            return decimal.Decimal(balance['free'])
        except BinanceAPIException as e:
            print(f"❌ Ошибка получения баланса XRP: {e.message}")
            return decimal.Decimal('0')

    def confirm_start(self):
        """Подтверждение запуска бота с проверкой баланса."""
        print("\n" + "="*50)
        print(f"📊 Параметры стратегии:")
        print(f"• Торговая пара: {SYMBOL}")
        print(f"• Цена активации: {START_PRICE} USDT")
        print(f"• Процент падения для покупки: {DECLINE_PERCENT}%")
        print(f"• Начальная сумма покупки: {INITIAL_AMOUNT} USDT")
        print(f"• Множитель суммы покупки: {MULTIPLIER}")
        print(f"• Максимальное количество шагов усреднения: {MAX_STEPS}")
        print(f"• Цель прибыли: {PROFIT_PERCENT}%")
        print(f"• Комиссия Binance: {COMMISSION*100}%")
        print(f"• Требуемый баланс для всех шагов: {self.required_balance} USDT")

        balance = self.get_usdt_balance()
        print(f"\n💰 Ваш текущий баланс: {balance} USDT")

        if balance < self.required_balance:
            print("\n⚠️ Внимание: Недостаточно средств для выполнения всех шагов!")
            print(f"Необходимо пополнить баланс минимум на {self.required_balance - balance:.2f} USDT")
            # Можно добавить опцию продолжить с меньшим количеством шагов или выйти

        # Добавлена проверка на минимальный размер ордера
        if INITIAL_AMOUNT < self.symbol_info['minNotional']:
            print(f"\n❌ Ошибка: Начальная сумма покупки ({INITIAL_AMOUNT:.2f} USDT) ниже минимального размера ордера Binance ({self.symbol_info['minNotional']:.2f} USDT).")
            print("Пожалуйста, увеличьте INITIAL_AMOUNT в настройках бота.")
            exit()

        choice = input("\nЗапустить бота? (yes/no): ").strip().lower()
        if choice != 'yes':
            print("Отмена запуска...")
            exit()
        print("="*50 + "\n")

    def get_current_price(self):
        """Получает текущую рыночную цену XRP."""
        try:
            ticker = client.get_symbol_ticker(symbol=SYMBOL)
            return decimal.Decimal(ticker['price'])
        except BinanceAPIException as e:
            print(f"❌ Ошибка получения текущей цены: {e.message}")
            return None
        except Exception as e:
            print(f"❌ Неизвестная ошибка при получении цены: {e}")
            return None

    def wait_for_start_price(self):
        """Ожидает, пока текущая цена достигнет или опустится ниже START_PRICE."""
        print(f"🕒 Ожидаем цену активации {START_PRICE} USDT...")
        while True:
            price = self.get_current_price()
            if price is None:
                time.sleep(3) # Ждем перед повторной попыткой
                continue

            print(f" Текущая цена: {price:.4f} USDT")
            # Активируем бота, когда цена достигает или опускается ниже START_PRICE
            if price <= START_PRICE:
                print(f"✅ Цена достигла {price:.4f} USDT, активируем бота!")
                self.entry_price = price # Фиксируем цену активации как entry_price
                return
            time.sleep(3) # Проверяем цену каждые 3 секунды

    def calculate_target_price(self, step):
        """
        Рассчитывает целевую цену для срабатывания текущего шага покупки усреднения.
        'step' здесь - это 0-индексированный номер шага усреднения (0 для первого, 1 для второго и т.д.).
        """
        # Целевая цена - это entry_price, уменьшенная на DECLINE_PERCENT для каждого шага усреднения.
        # Например, для step=0 (первое усреднение) падение будет на 1 * DECLINE_PERCENT
        # Для step=1 (второе усреднение) падение будет на 2 * DECLINE_PERCENT
        return self.entry_price * (1 - DECLINE_PERCENT/decimal.Decimal('100') * (step + 1))

    def buy_xrp(self, amount_usdt):
        """Покупает XRP на указанную сумму в USDT."""
        try:
            current_price = self.get_current_price()
            if not current_price:
                print("❌ Не удалось получить текущую цену для покупки.")
                return False

            # Проверяем минимальную сумму ордера (MIN_NOTIONAL)
            if amount_usdt < self.symbol_info['minNotional']:
                print(f"⚠️ Сумма покупки {amount_usdt:.2f} USDT ниже минимальной {self.symbol_info['minNotional']:.2f} USDT. Отмена покупки.")
                return False # Возвращаем False, чтобы не пытаться размещать невалидный ордер

            # Рассчитываем количество XRP для покупки
            # Используем Decimal для точных расчетов
            quantity_raw = amount_usdt / current_price
            quantity_to_buy = self._quantize_quantity(quantity_raw)

            # Проверяем минимальное количество
            if quantity_to_buy < self.symbol_info['minQty']:
                print(f"⚠️ Рассчитанное количество {quantity_to_buy:.4f} XRP ниже минимального {self.symbol_info['minQty']:.4f} XRP. Отмена покупки.")
                return False # Возвращаем False

            print(f"\n🛒 Покупаем {quantity_to_buy:.4f} XRP на сумму {amount_usdt:.2f} USDT по цене {current_price:.4f}")

            # Размещаем рыночный ордер на покупку
            order = client.create_order(
                symbol=SYMBOL,
                side=Client.SIDE_BUY,
                type=Client.ORDER_TYPE_MARKET,
                quantity=quantity_to_buy # Отправляем округленное количество
            )

            # Обработка ответа ордера
            executed_qty = decimal.Decimal(order['executedQty'])
            cummulative_quote_qty = decimal.Decimal(order['cummulativeQuoteQty']) # Общая сумма в USDT, включая комиссию

            # Комиссия в XRP (для покупки XRP/USDT, комиссия обычно в XRP)
            commission_xrp = executed_qty * COMMISSION
            net_received_xrp = executed_qty - commission_xrp

            self.total_quantity += net_received_xrp
            self.total_spent += cummulative_quote_qty # Общая сумма, которую мы фактически потратили в USDT

            print(f"✅ Куплено {net_received_xrp:.4f} XRP за {cummulative_quote_qty:.2f} USDT")
            print(f"💸 Удержано комиссии: {commission_xrp:.4f} XRP")
            return True

        except BinanceAPIException as e:
            print(f"❌ Ошибка покупки: {e.message} (Код: {e.code})")
            # Дополнительная обработка ошибок, например, недостаточно средств
            if e.code == -2010: # Код ошибки для "Недостаточно средств"
                print("🚨 Недостаточно средств на балансе USDT для этой покупки.")
            return False
        except Exception as e:
            print(f"❌ Неизвестная ошибка при выполнении покупки: {e}")
            return False

    def sell_all_xrp(self):
        """Продает все доступные XRP на балансе."""
        try:
            free_xrp = self.get_xrp_balance()
            # Проверяем, есть ли что продавать и соответствует ли минимальному количеству
            if free_xrp <= self.symbol_info['minQty']:
                print(f"ℹ️ Нет достаточного количества XRP для продажи ({free_xrp:.4f} <= {self.symbol_info['minQty']:.4f}).")
                self.reset_state() # Сбросить состояние, если нет монет для продажи
                return

            # Округляем количество XRP для продажи
            quantity_to_sell = self._quantize_quantity(free_xrp)

            print(f"\n💰 Продаем {quantity_to_sell:.4f} XRP...")
            order = client.create_order(
                symbol=SYMBOL,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=quantity_to_sell
            )

            executed_qty = decimal.Decimal(order['executedQty'])
            cummulative_quote_qty = decimal.Decimal(order['cummulativeQuoteQty']) # Полученная сумма в USDT

            # Комиссия в USDT (для продажи XRP/USDT, комиссия обычно в USDT)
            commission_usdt = cummulative_quote_qty * COMMISSION
            net_received_usdt = cummulative_quote_qty - commission_usdt

            print(f"✅ Продано {executed_qty:.4f} XRP, получено {net_received_usdt:.2f} USDT")
            print(f"� Удержано комиссии: {commission_usdt:.4f} USDT")
            self.reset_state() # Сброс состояния после успешной продажи

        except BinanceAPIException as e:
            print(f"❌ Ошибка продажи: {e.message} (Код: {e.code})")
            return
        except Exception as e:
            print(f"❌ Неизвестная ошибка при выполнении продажи: {e}")
            return

    def check_profit_condition(self):
        """Проверяет условие для фиксации прибыли."""
        if self.total_quantity == 0:
            return False # Нет купленных монет, нет прибыли

        avg_price = self.total_spent / self.total_quantity
        current_price = self.get_current_price()
        if not current_price:
            return False

        # Целевая цена продажи: средняя цена + PROFIT_PERCENT
        target_sell_price = avg_price * (1 + PROFIT_PERCENT/decimal.Decimal('100'))
        
        print(f"📈 Средняя цена покупки: {avg_price:.4f} USDT")
        print(f"🎯 Целевая цена продажи: {target_sell_price:.4f} USDT")
        print(f"💰 Текущая цена: {current_price:.4f} USDT")

        return current_price >= target_sell_price

    def reset_state(self):
        """Сбрасывает состояние бота для нового цикла торговли."""
        self.entry_price = None
        self.current_step = 0
        self.total_quantity = decimal.Decimal('0')
        self.total_spent = decimal.Decimal('0')
        self.next_buy_amount = INITIAL_AMOUNT
        print("\n♻️ Состояние бота сброшено. Ожидаем нового цикла.")

    def run(self):
        """Основной цикл работы бота."""
        # wait_for_start_price() вызывается только один раз при первом запуске
        # self.entry_price устанавливается здесь на фактическую цену активации

        # --- Выполняем начальную покупку по цене активации ---
        print(f"\n--- Выполняем первую покупку (начальный вход) ---")
        current_price = self.get_current_price()
        if current_price is None:
            print("❌ Не удалось получить текущую цену для первой покупки. Перезапуск бота.")
            self.reset_state() # Сброс состояния для нового цикла
            return

        # Первая покупка всегда на сумму INITIAL_AMOUNT
        print(f"🛒 Покупаем {INITIAL_AMOUNT:.2f} USDT XRP по текущей цене {current_price:.4f}")
        if self.buy_xrp(INITIAL_AMOUNT):
            # После успешной начальной покупки, устанавливаем next_buy_amount для первого шага DCA
            self.next_buy_amount = INITIAL_AMOUNT * MULTIPLIER
            self.current_step = 0 # Это 0-й шаг усреднения (первое падение после начальной покупки)
            # Проверяем условие прибыли сразу после начальной покупки (маловероятно, но возможно)
            if self.check_profit_condition():
                print(f"\n🎯 Условие прибыли достигнуто сразу после начальной покупки! Продаем все XRP.")
                self.sell_all_xrp()
                return
        else:
            print("⚠️ Начальная покупка не удалась. Перезапуск бота.")
            self.reset_state()
            return # Если начальная покупка не удалась, перезапускаем бот

        # --- Продолжаем с MAX_STEPS шагами усреднения ---
        # Цикл теперь итерируется от current_step 0 до MAX_STEPS-1,
        # представляя 1-ю, 2-ю, ..., MAX_STEPS-ю покупки усреднения.
        # Общее количество покупок будет 1 (начальная) + MAX_STEPS (усреднение).
        while self.current_step < MAX_STEPS:
            current_price = self.get_current_price()
            if current_price is None:
                time.sleep(3)
                continue

            # calculate_target_price(self.current_step) корректно рассчитает
            # цель для 1-го падения (когда self.current_step=0), 2-го падения (self.current_step=1) и т.д.
            target_buy_price = self.calculate_target_price(self.current_step)

            print(f"\n--- Шаг усреднения {self.current_step + 1}/{MAX_STEPS} ---")
            print(f"Текущая цена: {current_price:.4f} USDT")
            print(f"Целевая цена для покупки: {target_buy_price:.4f} USDT (падение на {DECLINE_PERCENT * (self.current_step + 1)}% от {self.entry_price:.4f})")
            print(f"Сумма для следующей покупки: {self.next_buy_amount:.2f} USDT")
            print(f"Всего потрачено: {self.total_spent:.2f} USDT")
            print(f"Всего XRP: {self.total_quantity:.4f}")

            # Добавление вывода средней цены покупки и целевой цены продажи
            if self.total_quantity > 0:
                avg_price = self.total_spent / self.total_quantity
                target_sell_price_for_display = avg_price * (1 + PROFIT_PERCENT/decimal.Decimal('100'))
                print(f"📊 Средняя цена всех покупок: {avg_price:.4f} USDT")
                print(f"🎯 Целевая цена продажи для усреднения: {target_sell_price_for_display:.4f} USDT")
            else:
                print("📊 Средняя цена покупок: Пока нет купленных XRP.")
                print("🎯 Целевая цена продажи: N/A")


            # Проверка условия для покупки усреднения
            if current_price <= target_buy_price:
                print(f"✅ Цена {current_price:.4f} достигла или опустилась ниже целевой {target_buy_price:.4f}. Выполняем усредняющую покупку!")
                if self.buy_xrp(self.next_buy_amount):
                    self.next_buy_amount *= MULTIPLIER
                    self.current_step += 1
                    # После каждой покупки проверяем условие прибыли
                    if self.check_profit_condition():
                        print(f"\n🎯 Условие прибыли достигнуто! Продаем все XRP.")
                        self.sell_all_xrp()
                        return # Завершаем текущий цикл run(), чтобы начать новый
                else:
                    # Если покупка не удалась, не увеличиваем шаг и не меняем сумму
                    print("⚠️ Усредняющая покупка не удалась. Повторная попытка на этом же шаге.")
            else:
                print(f"Ожидаем падения цены до {target_buy_price:.4f} USDT для усреднения...")

            time.sleep(3) # Пауза перед следующей проверкой цены

        print("\n⚠️ Достигнут максимум шагов усреднения. Ожидаем условия для продажи...")
        # Если все шаги пройдены, бот ждет только условия для продажи
        while True:
            if self.check_profit_condition():
                print(f"\n🎯 Условие прибыли достигнуто! Продаем все XRP.")
                self.sell_all_xrp()
                break # Выход из цикла ожидания продажи
            time.sleep(5) # Ждем дольше, если все шаги выполнены

if __name__ == "__main__":
    bot = TradingBot()
    # Запрос подтверждения только при первом запуске скрипта
    bot.confirm_start()
    bot.wait_for_start_price() # Ожидание цены активации также происходит только один раз

    # Бесконечный цикл для перезапуска бота после каждого полного цикла (покупка/продажа)
    while True:
        try:
            bot.run()
            print("\n🔄 Бот завершил цикл. Перезапуск через 5 секунд...")
            time.sleep(5)
        except KeyboardInterrupt:
            # Обработка прерывания Ctrl+C
            choice = input("\nВыход. Продать все позиции перед выходом? (yes/no): ").strip().lower()
            if choice == 'yes':
                bot.sell_all_xrp()
            print("Завершение работы бота.")
            break
            else:
                break
        except Exception as e:
            print(f"🚨 Критическая ошибка в основном цикле: {e}")
            print("Перезапуск бота после критической ошибки через 10 секунд...")
            time.sleep(10)
