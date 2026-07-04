"""UI translation catalog for SKINRUSH (single source of truth).

The whole string catalog lives here on the backend. It is served to the thin
front-end via /api/i18n/ and the chosen language is stored in the session, so
backend-rendered strings (e.g. daily-task labels) stay in sync with the UI.

Rarity tier labels and wear names are CS2 terminology and stay in English on
purpose (as in the original site).
"""

LANGS = ["uz", "ru", "en"]
DEFAULT_LANG = "uz"

STRINGS = {
    "uz": {
        "lang_name": "O‘zbekcha",
        # nav
        "nav_bonuslar": "BONUSLAR", "nav_keyslar": "KEYSLAR",
        "nav_janglar": "KEYS JANGLAR", "nav_kontraktlar": "KONTRAKTLAR",
        "nav_yaxshilash": "YAXSHILASH", "nav_dokon": "DO'KON",
        "nav_inventar": "INVENTAR", "nav_dostlar": "DO'STLAR",
        # header
        "online": "online", "login": "Kirish",
        # daily
        "daily_title": "Kunlik sovg'a",
        "daily_sub": "Har kuni saytga kiring va bepul coin oling!",
        "daily_next": "Keyingi sovg'a:", "daily_claim": "Oling",
        "day_label": "{n}-kun", "day_key": "Keys",
        # tasks
        "tasks_title": "Topshiriqlar",
        "tasks_sub": "Topshiriqlarni bajaring va ko'proq coin yutib oling!",
        "tasks_all": "Barcha topshiriqlar ›",
        "task_login": "Saytga kiring",
        "task_profile": "Profilingizni to'ldiring",
        "task_telegram": "Telegram kanalga obuna bo'ling",
        "task_invite": "Do'stingizni taklif qiling",
        # user stats
        "stat_coin": "Mening coinim", "stat_streak": "Ketma-ket kunlar",
        "stat_invited": "Taklif qilingan do'stlar", "stat_won": "Jami yutgan coin",
        # cases
        "cases_title": "Keyslar", "search_ph": "Key qidirish...",
        "min_ph": "Min narx", "max_ph": "Max narx",
        # upgrade
        "upg_title": "Upgrade — skinni yaxshilash",
        "upg_your": "Sizning narsangiz", "upg_pick_inv": "Inventardan tanlang",
        "upg_target": "Nishon", "upg_pick_target": "Nishonni tanlang",
        "upg_btn": "Upgrade", "upg_inv_title": "Inventaringiz",
        "upg_search_ph": "skin qidirish...", "upg_empty": "Inventar bo'sh",
        "upg_need_higher": "nishon qimmatroq bo'lsin",
        "upg_pick_target_hint": "nishonni tanlang",
        "upg_result_win": "Muvaffaqiyat! {name} — ",
        "upg_result_lose": "Omadsiz. {name} yo'qoldi.",
        # case view
        "back": "‹ Orqaga", "open_btn": "Ochish", "view_btn": "Ko'rish",
        "close_btn": "Yopish", "sell_btn": "Sotish", "sound": "Ovozi",
        "contents_title": "Ushbu keydagi narsalar",
        # detail rows
        "row_weapon": "Qurol", "row_finish": "Chizma", "row_wear": "Holati",
        "row_float": "Float", "row_rarity": "Noyoblik", "row_value": "Qiymati",
        "row_type": "Turi", "row_wears_all": "Holatlari",
        "row_drop_chance": "Tushish ehtimoli",
        "type_knife": "Pichoq / Qo'lqop", "type_weapon": "Qurol skini",
        # toasts
        "toast_win": "Yutuq: {name} · {price} coin",
        "toast_sold": "Sotildi: {name} · +{price} coin",
        "toast_login": "Kirish — demo rejimida faol emas",
        "toast_lang": "Til: {lang}",
        "toast_section": "Bu bo'lim demo versiyada mavjud emas",
        "toast_daily": "Kunlik sovg'a olindi! +{n} coin",
        "toast_upg_win": "Upgrade muvaffaqiyatli: {name}",
        "toast_upg_lose": "Upgrade omadsiz tugadi",
        "toast_tasks_all": "Barcha topshiriqlar — demo versiyada mavjud emas",
        # footer
        "footer_desc": "CS2 keyslarini oching, noyob skinlarni yutib oling. Bu demo-loyiha — haqiqiy pul ishlatilmaydi.",
        "footer_pages": "Sahifalar", "footer_help": "Yordam", "footer_faq": "FAQ",
        "footer_support": "Qo'llab-quvvatlash", "footer_terms": "Foydalanish shartlari",
        "footer_link_cases": "Keyslar", "footer_link_contracts": "Kontraktlar",
        "footer_link_shop": "Do'kon", "footer_link_inventory": "Inventar",
        "footer_18_title": "18+",
        "footer_18": "Faqat 18 yoshdan oshgan foydalanuvchilar uchun. Mas'uliyat bilan o'ynang.",
        "footer_bottom": "© 2026 SKINRUSH. Barcha huquqlar himoyalangan. · Demo maqsadida yaratilgan.",
    },
    "ru": {
        "lang_name": "Русский",
        "nav_bonuslar": "БОНУСЫ", "nav_keyslar": "КЕЙСЫ",
        "nav_janglar": "БИТВЫ КЕЙСОВ", "nav_kontraktlar": "КОНТРАКТЫ",
        "nav_yaxshilash": "АПГРЕЙД", "nav_dokon": "МАГАЗИН",
        "nav_inventar": "ИНВЕНТАРЬ", "nav_dostlar": "ДРУЗЬЯ",
        "online": "онлайн", "login": "Войти",
        "daily_title": "Ежедневный подарок",
        "daily_sub": "Заходите каждый день и получайте бесплатные коины!",
        "daily_next": "Следующий подарок:", "daily_claim": "Забрать",
        "day_label": "День {n}", "day_key": "Кейс",
        "tasks_title": "Задания",
        "tasks_sub": "Выполняйте задания и получайте больше коинов!",
        "tasks_all": "Все задания ›",
        "task_login": "Зайдите на сайт",
        "task_profile": "Заполните профиль",
        "task_telegram": "Подпишитесь на Telegram-канал",
        "task_invite": "Пригласите друга",
        "stat_coin": "Мои коины", "stat_streak": "Дней подряд",
        "stat_invited": "Приглашённые друзья", "stat_won": "Всего выиграно коинов",
        "cases_title": "Кейсы", "search_ph": "Поиск кейса...",
        "min_ph": "Мин. цена", "max_ph": "Макс. цена",
        "upg_title": "Апгрейд — улучшение скина",
        "upg_your": "Ваш предмет", "upg_pick_inv": "Выберите из инвентаря",
        "upg_target": "Цель", "upg_pick_target": "Выберите цель",
        "upg_btn": "Апгрейд", "upg_inv_title": "Ваш инвентарь",
        "upg_search_ph": "поиск скина...", "upg_empty": "Инвентарь пуст",
        "upg_need_higher": "цель должна быть дороже",
        "upg_pick_target_hint": "выберите цель",
        "upg_result_win": "Успех! {name} — ",
        "upg_result_lose": "Неудача. {name} потерян.",
        "back": "‹ Назад", "open_btn": "Открыть", "view_btn": "Посмотреть",
        "close_btn": "Закрыть", "sell_btn": "Продать", "sound": "Звук",
        "contents_title": "Содержимое кейса",
        "row_weapon": "Оружие", "row_finish": "Рисунок", "row_wear": "Состояние",
        "row_float": "Флоат", "row_rarity": "Редкость", "row_value": "Стоимость",
        "row_type": "Тип", "row_wears_all": "Состояния",
        "row_drop_chance": "Шанс выпадения",
        "type_knife": "Нож / Перчатки", "type_weapon": "Скин оружия",
        "toast_win": "Выигрыш: {name} · {price} коинов",
        "toast_sold": "Продано: {name} · +{price} коинов",
        "toast_login": "Вход — недоступен в демо-режиме",
        "toast_lang": "Язык: {lang}",
        "toast_section": "Этот раздел недоступен в демо-версии",
        "toast_daily": "Ежедневный подарок получен! +{n} коинов",
        "toast_upg_win": "Апгрейд успешен: {name}",
        "toast_upg_lose": "Апгрейд не удался",
        "toast_tasks_all": "Все задания — недоступно в демо-версии",
        "footer_desc": "Открывайте кейсы CS2 и выигрывайте редкие скины. Это демо-проект — реальные деньги не используются.",
        "footer_pages": "Страницы", "footer_help": "Помощь", "footer_faq": "FAQ",
        "footer_support": "Поддержка", "footer_terms": "Условия использования",
        "footer_link_cases": "Кейсы", "footer_link_contracts": "Контракты",
        "footer_link_shop": "Магазин", "footer_link_inventory": "Инвентарь",
        "footer_18_title": "18+",
        "footer_18": "Только для пользователей старше 18 лет. Играйте ответственно.",
        "footer_bottom": "© 2026 SKINRUSH. Все права защищены. · Создано в демонстрационных целях.",
    },
    "en": {
        "lang_name": "English",
        "nav_bonuslar": "BONUSES", "nav_keyslar": "CASES",
        "nav_janglar": "CASE BATTLES", "nav_kontraktlar": "CONTRACTS",
        "nav_yaxshilash": "UPGRADE", "nav_dokon": "SHOP",
        "nav_inventar": "INVENTORY", "nav_dostlar": "FRIENDS",
        "online": "online", "login": "Sign in",
        "daily_title": "Daily reward",
        "daily_sub": "Log in every day and get free coins!",
        "daily_next": "Next reward:", "daily_claim": "Claim",
        "day_label": "Day {n}", "day_key": "Case",
        "tasks_title": "Tasks",
        "tasks_sub": "Complete tasks and earn more coins!",
        "tasks_all": "All tasks ›",
        "task_login": "Visit the site",
        "task_profile": "Complete your profile",
        "task_telegram": "Subscribe to the Telegram channel",
        "task_invite": "Invite a friend",
        "stat_coin": "My coins", "stat_streak": "Day streak",
        "stat_invited": "Invited friends", "stat_won": "Total coins won",
        "cases_title": "Cases", "search_ph": "Search cases...",
        "min_ph": "Min price", "max_ph": "Max price",
        "upg_title": "Upgrade — improve your skin",
        "upg_your": "Your item", "upg_pick_inv": "Pick from inventory",
        "upg_target": "Target", "upg_pick_target": "Pick a target",
        "upg_btn": "Upgrade", "upg_inv_title": "Your inventory",
        "upg_search_ph": "search skins...", "upg_empty": "Inventory is empty",
        "upg_need_higher": "target must be worth more",
        "upg_pick_target_hint": "pick a target",
        "upg_result_win": "Success! {name} — ",
        "upg_result_lose": "Unlucky. {name} lost.",
        "back": "‹ Back", "open_btn": "Open", "view_btn": "View",
        "close_btn": "Close", "sell_btn": "Sell", "sound": "Sound",
        "contents_title": "Items in this case",
        "row_weapon": "Weapon", "row_finish": "Finish", "row_wear": "Wear",
        "row_float": "Float", "row_rarity": "Rarity", "row_value": "Value",
        "row_type": "Type", "row_wears_all": "Wears",
        "row_drop_chance": "Drop chance",
        "type_knife": "Knife / Gloves", "type_weapon": "Weapon skin",
        "toast_win": "Win: {name} · {price} coins",
        "toast_sold": "Sold: {name} · +{price} coins",
        "toast_login": "Sign in — disabled in demo mode",
        "toast_lang": "Language: {lang}",
        "toast_section": "This section is not available in the demo",
        "toast_daily": "Daily reward claimed! +{n} coins",
        "toast_upg_win": "Upgrade successful: {name}",
        "toast_upg_lose": "Upgrade failed",
        "toast_tasks_all": "All tasks — not available in the demo",
        "footer_desc": "Open CS2 cases and win rare skins. This is a demo project — no real money is used.",
        "footer_pages": "Pages", "footer_help": "Help", "footer_faq": "FAQ",
        "footer_support": "Support", "footer_terms": "Terms of use",
        "footer_link_cases": "Cases", "footer_link_contracts": "Contracts",
        "footer_link_shop": "Shop", "footer_link_inventory": "Inventory",
        "footer_18_title": "18+",
        "footer_18": "For users aged 18 and over only. Play responsibly.",
        "footer_bottom": "© 2026 SKINRUSH. All rights reserved. · Made for demonstration purposes.",
    },
}


def get_lang(request):
    lang = request.session.get("lang", DEFAULT_LANG)
    return lang if lang in STRINGS else DEFAULT_LANG


def strings_for(lang):
    return STRINGS.get(lang, STRINGS[DEFAULT_LANG])


def t(lang, key):
    return strings_for(lang).get(key, STRINGS[DEFAULT_LANG].get(key, key))
