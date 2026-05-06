import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import threading
import time
import random
import re
import pymorphy3
from spellchecker import SpellChecker


# =========================================================
# 1. КЛАСС: WordProcessor (Лингвистическая логика)
# =========================================================
class WordProcessor:
    def __init__(self):
        self.morph = pymorphy3.MorphAnalyzer()
        self.spell_en = SpellChecker(language='en')

    def normalize_ru(self, word):
        """Проверка и нормализация русского слова."""
        word = word.lower().strip()
        if not re.match(r'^[а-яё\-]+$', word): return None
        parsed = self.morph.parse(word)[0]
        if 'UNKN' in parsed.tag: return None
        return parsed.normal_form

    def verify_en(self, word):
        """Проверка английского слова по словарю."""
        word = word.lower().strip()
        if not re.match(r'^[a-z\-]+$', word): return None
        return word if word in self.spell_en else None


# =========================================================
# 2. КЛАСС: DictionaryManager (Хранилище данных)
# =========================================================
class DictionaryManager:
    def __init__(self):
        self._storage = {}

    def add(self, ru, en):
        self._storage[ru] = en

    def is_duplicate(self, word):
        """Проверка: существует ли уже такое слово в словаре."""
        word = word.lower().strip()
        return word in self._storage or word in self._storage.values()

    def get_translation(self, word):
        """Поиск перевода в обе стороны."""
        if word in self._storage: return self._storage[word]
        for ru, en in self._storage.items():
            if en == word: return ru
        return None

    def get_all(self):
        return self._storage


# =========================================================
# 3. КЛАСС: StateManager (Управление состояниями пользователей)
# =========================================================
class StateManager:
    def __init__(self):
        self._users = {}

    def get_user(self, uid):
        if uid not in self._users:
            self._users[uid] = {
                'state': 'normal',
                'interval': 300,
                'last_quiz': time.time()
            }
        return self._users[uid]

    def set_val(self, uid, key, value):
        user = self.get_user(uid)
        user[key] = value

    def reset(self, uid):
        user = self.get_user(uid)
        user['state'] = 'normal'
        user.pop('ru', None)
        user.pop('ans', None)

    def get_all_users(self):
        return self._users


# =========================================================
# 4. КЛАСС: KeyboardProvider (Интерфейс)
# =========================================================
class KeyboardProvider:
    @staticmethod
    def get_main():
        kb = VkKeyboard(one_time=False)
        kb.add_button('➕ Добавить слово', color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button('📖 Мой словарь', color=VkKeyboardColor.SECONDARY)
        kb.add_button('🕘 Поменять время для викторины!', color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def get_settings():
        kb = VkKeyboard(one_time=True)
        kb.add_button('1 мин', color=VkKeyboardColor.PRIMARY)
        kb.add_button('5 мин', color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button('15 мин', color=VkKeyboardColor.PRIMARY)
        kb.add_button('30 мин', color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button('❌ Отмена', color=VkKeyboardColor.NEGATIVE)
        return kb.get_keyboard()

    @staticmethod
    def get_cancel():
        kb = VkKeyboard(one_time=True)
        kb.add_button('❌ Отмена', color=VkKeyboardColor.NEGATIVE)
        return kb.get_keyboard()

    @staticmethod
    def get_quiz_keyboard(options):
        if not options: return None
        kb = VkKeyboard(one_time=True)
        for i, word in enumerate(options):
            kb.add_button(word, color=VkKeyboardColor.PRIMARY)
            if i < len(options) - 1: kb.add_line()
        return kb.get_keyboard()


# =========================================================
# 5. КЛАСС: BotOrchestrator (Сердце бота)
# =========================================================
class BotOrchestrator:
    def __init__(self, token):
        self.session = vk_api.VkApi(token=token)
        self.vk = self.session.get_api()
        self.longpoll = VkLongPoll(self.session)

        self.db = DictionaryManager()
        self.states = StateManager()
        self.words = WordProcessor()
        self.ui = KeyboardProvider()

    def send(self, uid, text, kb=None):
        self.vk.messages.send(
            user_id=uid, message=text,
            random_id=get_random_id(), keyboard=kb
        )

    def _scheduler_thread(self):
        while True:
            time.sleep(10)
            now = time.time()
            all_words = self.db.get_all()
            if not all_words: continue

            for uid, data in self.states.get_all_users().items():
                if now - data['last_quiz'] >= data['interval'] and data['state'] == 'normal':
                    self._trigger_quiz(uid, all_words)
                    data['last_quiz'] = now

    def _trigger_quiz(self, uid, dictionary):
        count = len(dictionary)
        ru_key = random.choice(list(dictionary.keys()))
        en_val = dictionary[ru_key]
        direction = random.randint(0, 1)

        if direction == 0:
            q, ans, pool = ru_key, en_val, list(dictionary.values())
        else:
            q, ans, pool = en_val, ru_key, list(dictionary.keys())

        kb = None
        if count >= 3:
            others = [v for v in pool if v != ans]
            vars_list = random.sample(others, 2) + [ans]
            random.shuffle(vars_list)
            kb = self.ui.get_quiz_keyboard(vars_list)
        elif count == 2:
            others = [v for v in pool if v != ans]
            vars_list = [ans, others[0]]
            random.shuffle(vars_list)
            kb = self.ui.get_quiz_keyboard(vars_list)

        self.send(uid, f"⏰ Время повторения! Как переводится: {q}?", kb)
        self.states.set_val(uid, 'state', 'quiz')
        self.states.set_val(uid, 'ans', ans)

    def start(self):
        threading.Thread(target=self._scheduler_thread, daemon=True).start()
        print("Бот запущен и готов к работе! 🐇")
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                self._handle(event.user_id, event.text.lower().strip())

    def _handle(self, uid, text):
        user_data = self.states.get_user(uid)
        state = user_data['state']

        if text == 'начать':
            self.states.reset(uid)
            welcome = (
                "Приветствую! Я бот-словарь для помощи в изучении английского языка!🤍\n"
                "Мой функционал достаточно прост: ты записываешь слова и их перевод.☕\n"
                "Я буду периодически проверять твои знания!🐇"
            )
            self.send(uid, welcome, self.ui.get_main())
            return

        if text in ['❌ отмена', '❌ в главное меню']:
            self.states.reset(uid)
            self.send(uid, "Вы в главном меню🧺\nДобавьте слово или подождите викторины!☕", self.ui.get_main())
            return

        if text == '➕ добавить слово' and state == 'normal':
            self.states.set_val(uid, 'state', 'wait_ru')
            self.send(uid, "Введите слово на русском:", self.ui.get_cancel())
            return

        if text == '📖 мой словарь' and state == 'normal':
            d = self.db.get_all()
            msg = "\n".join([f"✨ {k} — {v}" for k, v in d.items()]) if d else "Твой словарик пока пуст.☕"
            self.send(uid, msg, self.ui.get_main())
            return

        if text == '🕘 поменять время для викторины!' and state == 'normal':
            self.states.set_val(uid, 'state', 'set_timer')
            self.send(uid, "Как часто проверять вашу память?☁", self.ui.get_settings())
            return

        if state == 'set_timer':
            times = {'1 мин': 60, '5 мин': 300, '15 мин': 900, '30 мин': 1800}
            if text in times:
                self.states.set_val(uid, 'interval', times[text])
                self.states.set_val(uid, 'last_quiz', time.time())
                self.states.reset(uid)
                self.send(uid, f"Ясно! Теперь я буду писать вам каждые {text}!⛅", self.ui.get_main())
            else:
                self.send(uid, "Пожалуйста, выберите время на кнопках.☁", self.ui.get_settings())

        elif state == 'wait_ru':
            if self.db.is_duplicate(text):
                self.send(uid, "Это слово уже есть в твоем словаре!☕\nПопробуй другое:", self.ui.get_cancel())
                return

            res = self.words.normalize_ru(text)
            if res:
                self.states.set_val(uid, 'state', 'wait_en')
                self.states.set_val(uid, 'ru', res)
                self.send(uid, f"Введите английский перевод для '{res}':", self.ui.get_cancel())
            else:
                self.send(uid, "Прости, я не знаю такого слова.☕\nПопробуй еще раз:", self.ui.get_cancel())

        elif state == 'wait_en':
            if self.db.is_duplicate(text):
                self.send(uid, "Такой перевод уже закреплен за каким-то словом!☕\nПопробуй другой:",
                          self.ui.get_cancel())
                return

            res = self.words.verify_en(text)
            if res:
                self.db.add(user_data['ru'], res)
                self.states.reset(uid)
                self.send(uid, "Слово сохранено! Ты молодец!✨", self.ui.get_main())
            else:
                self.send(uid, "Кажется, в английском слове ошибка.☕\nПопробуй еще раз:", self.ui.get_cancel())

        elif state == 'quiz':
            if text == user_data['ans']:
                self.send(uid, "🌟 Верно! Ты супер! 🌟", self.ui.get_main())
            else:
                self.send(uid, f"😔 Нет, правильный ответ: {user_data['ans']}. В следующий раз получится! 😁",
                          self.ui.get_main())
            self.states.reset(uid)

        elif state == 'normal':
            t = self.db.get_translation(text)
            if t:
                self.send(uid, f"🔍 Перевод: {t}", self.ui.get_main())
            else:
                self.send(uid, "Я не знаю такого слова.☕\nИспользуй меню!", self.ui.get_main())


if __name__ == "__main__":
    TOKEN = "meow"
    bot = BotOrchestrator(TOKEN)
    bot.start()