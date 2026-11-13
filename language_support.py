"""Supported interface locales and regional Traditional Chinese review text."""
from functools import lru_cache

from opencc import OpenCC

LANGUAGES = ('zh', 'zh-HK', 'zh-TW', 'en')


@lru_cache(maxsize=2)
def _converter(language):
    return OpenCC('s2hk' if language == 'zh-HK' else 's2twp')


def localized_text(text, language):
    if language == 'zh':
        return _simplified_converter().convert(text)
    return _converter(language).convert(text) if language in ('zh-HK', 'zh-TW') else text


@lru_cache(maxsize=1)
def _simplified_converter():
    return OpenCC('t2s')


def review_instruction(language):
    if language == 'en':
        return 'All generated text fields, emotions and activity titles must be in English; keep activity_id/category unchanged. Each emotion must be at most 40 characters, each activity title at most 80 characters, each activity description at most 400 characters (characters, not words).'
    if language == 'zh-HK':
        return '所有文字字段使用繁體中文（中國香港），採用香港慣用字詞及書面語；activity_id/category保持不變。'
    if language == 'zh-TW':
        return '所有文字字段使用繁體中文（中國台灣），採用台灣慣用字詞；activity_id/category保持不變。'
    return '所有文字字段用简体中文。'


def localize_review(result, language):
    if language not in ('zh-HK', 'zh-TW'):
        return result
    result['emotions'] = [localized_text(value, language) for value in result['emotions']]
    for field in ('summary', 'food', 'vitamins', 'movement', 'inspiration'):
        result[field] = localized_text(result[field], language)
    for step in result['activity_plan']:
        for field in ('title', 'description'):
            step[field] = localized_text(step[field], language)
    return result
