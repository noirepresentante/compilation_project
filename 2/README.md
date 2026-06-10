
---

## Запуск ЛР1

```bash
python preprocessor/preprocess.py test/test.cpp -o test/test.cleaned.cpp
```

---

## Запуск ЛР2 на уже очищенном коде

```bash
python lexer/lexer.py test/test.cleaned.cpp
```

## Запуск ЛР2 сразу на исходном файле с использованием ЛР1

```bash
python lexer/lexer.py test/test.cpp --raw --save-cleaned test/test.cleaned.cpp
```

## Сохранение результатов в отдельные файлы

```bash
python lexer/lexer.py test/test.cleaned.cpp \
  --out-tables test/lexeme_tables.txt \
  --out-tokens test/tokens.txt \
  --out-sequence test/token_sequence.json
```

---