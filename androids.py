import datetime
import json
import threading

import cv2
import pymysql
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from pyzbar import pyzbar

DB_CONFIG = {
    "host": "194.87.243.9",
    "user": "pedr",
    "password": "15421542",
    "database": "fridge_management",
    "charset": "utf8mb4"
}


def check_product_in_db(product_name):
    """Проверяет, есть ли продукт в базе. Возвращает dict или None."""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        sql = "SELECT * FROM products WHERE product_name = %s LIMIT 1;"
        cursor.execute(sql, (product_name,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()
        return product
    except pymysql.MySQLError as err:
        print("Ошибка MySQL:", err)
        return None


def delete_product_from_db(product_name):
    """Удаляет продукт (физически) из таблицы products."""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        sql = "DELETE FROM products WHERE product_name = %s;"
        cursor.execute(sql, (product_name,))
        conn.commit()
        cursor.close()
        conn.close()
    except pymysql.MySQLError as err:
        print("Ошибка MySQL:", err)


def days_until_expiration(expiration_date):
    """Вычисляет, сколько дней осталось до истечения срока годности."""
    if not expiration_date:
        return None
    exp_date = expiration_date if isinstance(expiration_date, datetime.date) else \
        datetime.datetime.strptime(expiration_date, "%Y-%m-%d").date()
    today = datetime.date.today()
    return (exp_date - today).days


def format_days_left(days_left):
    """Форматирует количество дней в строку для отображения."""
    if days_left is None:
        return "Неизвестно"
    if days_left < 0:
        return f"Истек {abs(days_left)} дней назад"
    return f"Осталось {days_left} дней"


class MainScreen(Screen):
    def scan_qr(self):
        """Метод для обработки нажатия на кнопку 'Скан QR'."""
        self.manager.current = 'scanqr'

    def open_shopping_list(self):
        """Метод для открытия списка покупок."""
        self.manager.current = 'shopping_list'

    def on_pre_enter(self):
        """Добавляет кнопку 'Список покупок' на главный экран."""
        layout = self.ids.get("main_layout", None)
        if layout:
            shopping_list_button = Button(text="Список покупок", size_hint=(1, 0.1))
            shopping_list_button.bind(on_press=lambda instance: setattr(self.manager, 'current', 'shopping_list'))
            layout.add_widget(shopping_list_button)

    def show_notification(self, message):
        """Показывает всплывающее уведомление."""
        popup = Popup(
            title="Уведомление",
            content=Label(text=message),
            size_hint=(0.8, 0.4)
        )
        popup.open()


class FridgeScreen(Screen):
    def __init__(self, **kwargs):
        super(FridgeScreen, self).__init__(**kwargs)
        self.products_by_type = []
        self.on_enter = self.on_enter_screen

    def on_enter_screen(self):
        self.products_by_type = self.get_all_products()
        self.display_products()
        # Проверяем продукты, срок которых истекает
        self.check_expiring_products()

    def get_all_products(self):
        """Получение всех продуктов из базы данных."""
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            # Берём все продукты (не учитывая отдельную таблицу удаления)
            cursor.execute("SELECT * FROM products;")
            products = cursor.fetchall()
            for product in products:
                product["days_left"] = days_until_expiration(product["expiration_date"])
            cursor.close()
            conn.close()
            return products
        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)
            return []

    def display_products(self, search_query=None, product_type=None):
        """Отображение продуктов на экране с возможностью фильтрации."""
        if not hasattr(self, 'ids') or 'products_container' not in self.ids:
            print("Ошибка: products_container не найден!")
            return

        products_container = self.ids.products_container
        products_container.clear_widgets()

        # Фильтрация продуктов
        # Меняем на поиск по подстроке и для типа
        filtered_products = []
        for p in self.products_by_type:
            name_match = (not search_query or search_query.lower() in p['product_name'].lower())
            type_match = (not product_type or product_type.lower() in p['product_type'].lower())
            if name_match and type_match:
                filtered_products.append(p)

        # Группируем продукты по типам
        grouped_products = self.group_products_by_type(filtered_products)

        # Отображение продуктов
        for p_type, products in grouped_products.items():
            self.add_type_label(products_container, p_type)
            for product in products:
                self.add_product_card(products_container, product)

    def group_products_by_type(self, products):
        """Группирует продукты по типам."""
        grouped_products = {}
        for product in products:
            product_type = product['product_type']
            if product_type not in grouped_products:
                grouped_products[product_type] = []
            grouped_products[product_type].append(product)
        return grouped_products

    def add_type_label(self, container, product_type):
        """Добавляет заголовок типа продукта."""
        type_label = Label(
            text=f"[b]{product_type}[/b]",
            markup=True,
            font_size=20,
            color=(0.1, 0.1, 0.1, 1),
            size_hint_y=None,
            height=40
        )
        container.add_widget(type_label)

    def add_product_card(self, container, product):
        """Добавляет карточку продукта."""
        product_layout = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=250,
            padding=10,
            spacing=5
        )
        with product_layout.canvas.before:
            Color(rgba=(0.95, 0.95, 0.95, 1))
            RoundedRectangle(pos=product_layout.pos, size=product_layout.size, radius=[10])

        # Информация о продукте
        product_layout.add_widget(self.create_label(f"[b]Продукт:[/b] {product['product_name']}", 16))
        product_layout.add_widget(
            self.create_label(
                f"[b]Количество:[/b] {product['quantity']} {product['measurement_unit']}", 14)
        )
        product_layout.add_widget(
            self.create_label(f"[b]Аллергены:[/b] {product['allergens']}", 14)
        )

        # Срок годности
        days_left = product['days_left']
        days_text = self.format_days_left(days_left)
        days_color = self.get_days_left_color(days_left)
        product_layout.add_widget(self.create_label(f"[b]Срок годности:[/b] {days_text}", 14, days_color))

        # Кнопки
        delete_button = Button(
            text="Удалить",
            size_hint_y=None,
            height=40,
            background_color=(1, 0.2, 0.2, 1),
            on_press=lambda instance, p=product: self.delete_product(p)
        )
        product_layout.add_widget(delete_button)

        view_info_button = Button(
            text="Подробнее",
            size_hint_y=None,
            height=40,
            background_color=(0.2, 0.6, 1, 1),
            on_press=lambda instance, p=product: self.view_product_info(p)
        )
        product_layout.add_widget(view_info_button)

        container.add_widget(product_layout)

    def create_label(self, text, font_size, color=(0.2, 0.2, 0.2, 1)):
        """Создает Label с заданными параметрами."""
        return Label(
            text=text,
            markup=True,
            font_size=font_size,
            color=color,
            size_hint_y=None,
            height=30
        )

    def format_days_left(self, days_left):
        """Форматирует текст для отображения оставшихся дней."""
        if days_left is None:
            return "Неизвестно"
        elif days_left < 0:
            return f"Истек {abs(days_left)} дней назад"
        else:
            return f"Осталось {days_left} дней"

    def get_days_left_color(self, days_left):
        """Определяет цвет для отображения срока годности."""
        if days_left is None or days_left < 0:
            return (1, 0, 0, 1)  # Красный
        elif days_left < 3:
            return (1, 0.5, 0, 1)  # Оранжевый
        elif days_left <= 7:
            return (1, 0.8, 0, 1)  # Желтый
        else:
            return (0, 1, 0, 1)  # Зеленый

    def delete_product(self, product):
        """
        Удаление продукта: заносим данные о продукте в delated_products (включая expiration_date),
        затем физически удаляем продукт из products.
        Благодаря этому в аналитике статус у просроченных отображается корректно
        (если столбец 'status' в БД — GENERATED).
        """
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor()

            # Дней до истечения (для вывода в уведомлении)
            days_left = product.get('days_left', None)
            insert_query = """
                INSERT INTO deleted_products (product_name, product_type, expiration_date, deleted_at)
                VALUES (%s, %s, %s, NOW())
            """
            cursor.execute(insert_query, (
                product['product_name'],
                product['product_type'],
                product['expiration_date']
            ))

            delete_query = "DELETE FROM products WHERE id = %s;"
            cursor.execute(delete_query, (product['id'],))

            conn.commit()
            cursor.close()
            conn.close()

            # Удаляем его из локального списка, чтобы интерфейс сразу обновился
            if product in self.products_by_type:
                self.products_by_type.remove(product)
            self.display_products()

            if days_left is not None and days_left < 0:
                self.show_notification(f"Продукт '{product['product_name']}' удалён как просроченный.")
            else:
                self.show_notification(f"Продукт '{product['product_name']}' удалён (съеденный).")

        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)

    def search_products(self, search_query):
        """Функция поиска продуктов (с учётом типа)."""
        type_input = self.ids.type_input
        product_type = type_input.text.strip()
        self.display_products(search_query=search_query, product_type=product_type)

    def show_notification(self, message):
        """Показывает всплывающее уведомление."""
        popup = Popup(
            title="Уведомление",
            content=Label(text=message),
            size_hint=(0.8, 0.4)
        )
        popup.open()

    def add_product_via_qr(self):
        """Имитация добавления продукта через QR-код."""
        self.show_notification("Продукт успешно добавлен через QR!")

    def view_product_info(self, product):
        """Просмотр полной информации о продукте."""
        info_text = (
            f"Название: {product['product_name']}\n"
            f"Тип: {product['product_type']}\n"
            f"Дата изготовления: {product['production_date']}\n"
            f"Дата истечения срока годности: {product['expiration_date']}\n"
            f"Количество: {product['quantity']} {product['measurement_unit']}\n"
            f"Тип измерения: {product['measurement_type']}\n"
            f"Пищевая ценность: {product['nutritional_value']}\n"
            f"Аллергены: {product['allergens']}\n"
            f"Дата добавления: {product['date_added']}"
        )
        popup = Popup(title="Информация о продукте", content=Label(text=info_text), size_hint=(0.8, 0.6))
        popup.open()

    def check_expiring_products(self):
        """Показываем уведомление о продуктах, у которых срок годности <= 3 дней."""
        for product in self.products_by_type:
            days_left = product['days_left']
            if days_left is not None and days_left <= 3:
                if days_left < 0:
                    self.show_notification(
                        f"Внимание! Срок годности продукта '{product['product_name']}' "
                        f"истёк {abs(days_left)} дня назад!"
                    )
                else:
                    self.show_notification(
                        f"Внимание! Срок годности продукта '{product['product_name']}' "
                        f"истекает через {days_left} дней!"
                    )


class ScanQRScreen(Screen):
    def on_enter(self):
        """При входе на экран автоматически запускаем сканирование QR-кодов"""
        self.scan_qr_in_thread()

    def scan_qr_in_thread(self):
        """Запуск сканирования в отдельном потоке."""
        t = threading.Thread(target=self._scan_qr_loop, daemon=True)
        t.start()

    def _scan_qr_loop(self):
        """Метод, который работает в фоновом потоке. Выполняет блокирующий цикл."""
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            Clock.schedule_once(lambda dt: self.show_notification("Не удалось открыть камеру."), 0)
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Не удалось считать кадр.")
                break

            decoded_objects = pyzbar.decode(frame)
            for obj in decoded_objects:
                qr_data = obj.data.decode('utf-8', errors='replace')
                print("QR-код найден:", qr_data)
                try:
                    product_info = json.loads(qr_data)
                    Clock.schedule_once(lambda dt: self.process_scanned_data(product_info), 0)
                except json.JSONDecodeError:
                    print("Ошибка: JSON недействителен.")

            cv2.imshow("QR Scanner - ESC или Q", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        Clock.schedule_once(lambda dt: self.show_notification("Завершено сканирование."), 0)

    def show_notification(self, message):
        """Показывает всплывающее уведомление."""
        popup = Popup(
            title="Уведомление",
            content=Label(text=message),
            size_hint=(0.8, 0.4)
        )
        popup.open()

    def process_scanned_data(self, product_info):
        """Обрабатывает данные из QR-кода, проверяет наличие в БД, добавляет или предлагает варианты."""

        if not isinstance(product_info, dict):  # Проверяем, является ли product_info словарем
            self.show_notification("Ошибка: данные QR-кода некорректны.")
            return

        product_name = product_info.get("name")
        if not product_name:
            self.show_notification("Ошибка: в QR-коде отсутствует поле 'name'.")
            return

        existing_product = self.check_product_in_db(product_name)
        if existing_product:
            self.show_existing_product_popup(existing_product)
        else:
            self.insert_into_db(product_info)
            self.show_notification(f"Продукт '{product_name}' добавлен в холодильник!")

    def on_pre_enter(self):
        """Добавляет кнопку 'Назад' при входе в экран."""
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        back_button = Button(text="Назад", size_hint=(1, 0.1))
        back_button.bind(on_press=lambda instance: setattr(self.manager, 'current', 'main'))
        layout.add_widget(back_button)
        self.add_widget(layout)

    def check_product_in_db(self, product_name):
        """Проверяет, есть ли продукт в базе данных."""
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("SELECT * FROM products WHERE product_name = %s LIMIT 1;", (product_name,))
            product = cursor.fetchone()
            cursor.close()
            conn.close()
            return product
        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)
            return None

    def insert_into_db(self, product_info):
        """Добавляет новый продукт в таблицу products."""
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor()
            sql = """
                INSERT INTO products (
                    product_name, product_type, production_date, expiration_date,
                    quantity, measurement_unit, measurement_type, nutritional_value, allergens, date_added
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
            """
            values = (
                product_info.get("name"),
                product_info.get("type"),
                product_info.get("production_date"),
                product_info.get("expiration_date"),
                product_info.get("quantity"),
                product_info.get("measurement_unit"),
                product_info.get("measurement_type"),
                product_info.get("nutritional_value"),
                product_info.get("allergens")
            )
            cursor.execute(sql, values)
            conn.commit()
            cursor.close()
            conn.close()
        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)

    def show_existing_product_popup(self, product_dict):
        """Показывает Popup с вариантами действий, если продукт уже есть в базе."""
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        label = Label(text=f"Продукт '{product_dict['product_name']}' уже существует. Выберите действие:")
        popup_layout.add_widget(label)
        btn_layout = BoxLayout(orientation='horizontal', spacing=10)
        btn_view = Button(text="Посмотреть данные")
        btn_delete = Button(text="Удалить продукт")
        btn_view.bind(on_press=lambda instance: self.view_existing_product_info(product_dict))
        btn_delete.bind(on_press=lambda instance: self.delete_existing_product(product_dict))
        btn_layout.add_widget(btn_view)
        btn_layout.add_widget(btn_delete)
        popup_layout.add_widget(btn_layout)
        popup = Popup(title="Продукт уже есть в базе", content=popup_layout, size_hint=(0.8, 0.4))
        btn_view.bind(on_release=lambda *args: popup.dismiss())
        btn_delete.bind(on_release=lambda *args: popup.dismiss())
        popup.open()

    def delete_existing_product(self, product_dict):
        """Удаляет продукт из БД."""
        product_name = product_dict['product_name']
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM products WHERE product_name = %s;", (product_name,))
            conn.commit()
            cursor.close()
            conn.close()
            self.show_notification(f"Продукт '{product_name}' удалён из базы.")
        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)


class AnalyticsScreen(Screen):
    def show_analytics(self):
        """
        Показываем реальную таблицу с удалёнными продуктами.
        Подгружаем записи из 'deleted_products':
          - product_name
          - product_type
          - status (generated)
          - deleted_at
        и выводим их в GridLayout (id: analytics_grid) с нумерацией в первом столбце.
        """
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            query = """
                SELECT product_name, product_type, status, deleted_at
                FROM deleted_products
                ORDER BY deleted_at DESC;
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            grid = self.ids.analytics_grid
            grid.clear_widgets()

            if not rows:
                grid.add_widget(Label(text="Нет записей", color=(0, 0, 0, 1)))
                grid.add_widget(Label(text="—", color=(0, 0, 0, 1)))
                grid.add_widget(Label(text="—", color=(0, 0, 0, 1)))
                grid.add_widget(Label(text="—", color=(0, 0, 0, 1)))
                grid.add_widget(Label(text="—", color=(0, 0, 0, 1)))
            else:
                for i, row in enumerate(rows, start=1):
                    # 1) Номер строки
                    grid.add_widget(Label(text=str(i), color=(0, 0, 0, 1)))

                    # 2) Название продукта
                    grid.add_widget(Label(text=row["product_name"], color=(0, 0, 0, 1)))

                    # 3) Тип продукта
                    grid.add_widget(Label(text=row["product_type"], color=(0, 0, 0, 1)))

                    # 4) Статус (generated)
                    grid.add_widget(Label(text=row["status"], color=(0, 0, 0, 1)))

                    # 5) Дата/время удаления
                    deleted_str = str(row["deleted_at"]) if row["deleted_at"] else ""
                    grid.add_widget(Label(text=deleted_str, color=(0, 0, 0, 1)))

        except pymysql.MySQLError as err:
            print("Ошибка MySQL при получении аналитики:", err)


class ShoppingListScreen(Screen):
    def on_enter(self):
        self.load_shopping_list()

    def load_shopping_list(self):
        """Загружает список покупок из базы данных."""
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("SELECT * FROM shopping_list;")
            items = cursor.fetchall()
            cursor.close()
            conn.close()
        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)
            items = []

        shopping_container = self.ids.get("shopping_container")
        if shopping_container:
            shopping_container.clear_widgets()
            for item in items:
                box = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
                box.add_widget(
                    Label(text=f"{item['product_name']} ({item['quantity']} {item['unit']})", color=(0, 0, 1, 1)))
                delete_button = Button(text="Удалить", size_hint_x=0.3)
                delete_button.bind(on_press=lambda instance, i=item: self.remove_from_shopping_list(i['id']))
                box.add_widget(delete_button)
                shopping_container.add_widget(box)

    def add_to_shopping_list(self, product_name, quantity=1, unit="шт"):
        """Добавляет продукт в список покупок."""
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor()
            sql = "INSERT INTO shopping_list (product_name, quantity, unit) VALUES (%s, %s, %s);"
            cursor.execute(sql, (product_name, quantity, unit))
            conn.commit()
            cursor.close()
            conn.close()
        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)
        self.load_shopping_list()

    def remove_from_shopping_list(self, item_id):
        """Удаляет продукт из списка покупок."""
        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor()
            sql = "DELETE FROM shopping_list WHERE id = %s;"
            cursor.execute(sql, (item_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except pymysql.MySQLError as err:
            print("Ошибка MySQL:", err)
        self.load_shopping_list()


class MyApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(FridgeScreen(name='fridge'))
        sm.add_widget(AnalyticsScreen(name='analytics'))
        sm.add_widget(ShoppingListScreen(name='shopping_list'))
        sm.add_widget(ScanQRScreen(name='scanqr'))
        return sm


if __name__ == '__main__':
    Builder.load_file('design.kv')
    MyApp().run()
