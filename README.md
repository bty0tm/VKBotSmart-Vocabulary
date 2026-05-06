```mermaid
classDiagram
    %% Связи между классами
    BotOrchestrator *-- DictionaryManager : содержит
    BotOrchestrator *-- StateManager : управляет
    BotOrchestrator *-- WordProcessor : обрабатывает
    BotOrchestrator *-- KeyboardProvider : получает кнопки

    class BotOrchestrator {
        +session: VkApi
        +vk: VkApiMethod
        +longpoll: VkLongPoll
        +start()
        +send(uid, text, kb)
        -_handle(uid, text)
        -_trigger_quiz(uid, dictionary)
        -_scheduler_thread()
    }

    class DictionaryManager {
        -_storage: dict
        +add(ru, en)
        +is_duplicate(word) bool
        +get_translation(word) str
        +get_all() dict
    }

    class WordProcessor {
        +morph: MorphAnalyzer
        +spell_en: SpellChecker
        +normalize_ru(word) str
        +verify_en(word) str
    }

    class StateManager {
        -_users: dict
        +get_user(uid) dict
        +set_val(uid, key, value)
        +reset(uid)
        +get_all_users() dict
    }

    class KeyboardProvider {
        +get_main() JSON
        +get_settings() JSON
        +get_cancel() JSON
        +get_quiz_keyboard(options) JSON
    }