"""Generate reusable activity illustrations without sending diary text to the image API."""
import hashlib
import fcntl
import ipaddress
import json
import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests


from activity_catalog import CATALOG

ACTIVITIES = {item['id']: item['image_prompt'] for item in CATALOG}
PERSON_ACTIVITIES = {key for key,prompt in ACTIVITIES.items() if re.search(r'\b(person|people|friends|hands?|human)\b',prompt)}


class ImageError(Exception):
    pass


class ImageService:
    def __init__(self, directory, max_workers=2, gender=None):
        self.gender = gender
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.model = os.getenv('IMAGE_MODEL', 'gpt-image-2.6')
        self.base = os.getenv('IMAGE_BASE_URL', 'https://grsai.dakka.com.cn').rstrip('/')
        self.key = os.getenv('IMAGE_API_KEY', '')
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='activity-image')
        self.lock = threading.Lock()
        self.active = set()
        self.file_locks = {}

    def path(self, category, suffix):
        version = hashlib.sha256((self.model + ':warm-activity-v1' + (':'+self.gender if self.gender and category in PERSON_ACTIVITIES else '')).encode()).hexdigest()[:16]
        return self.directory / f'{version}-{category}.{suffix}'

    def _read(self, category):
        if self.path(category, 'image').exists():
            return {'status': 'succeeded', 'url': f'/api/activity-images/{category}/file' + ('?profile='+self.gender if self.gender else '')}
        try:
            value = json.loads(self.path(category, 'json').read_text())
            if value.get('status') == 'succeeded':
                value.update(status='failed', error='本地配图缓存缺失，请点击重试下载。')
            return value
        except (OSError, ValueError):
            return {'status': 'idle'}

    def _write(self, category, value):
        path = self.path(category, 'json')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value))
        temporary.replace(path)

    def statuses(self, categories):
        with self.lock:
            result = {}
            for category in categories:
                value = self._read(category)
                # A server restart must not leave a permanent spinner.
                if value['status'] in ('queued', 'running') and category not in self.active and not self._externally_active(category):
                    value = {'status': 'failed', 'error': '配图生成中断，请点击重试。'}
                result[category] = {k: v for k, v in value.items() if k in ('status', 'url', 'error')}
            return result

    def _externally_active(self, category):
        with self.path(category, 'lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
            return False

    def start(self, categories, retry=False):
        if not self.key:
            return {c: {'status': 'unconfigured', 'error': '尚未配置图片服务，暂用活动示意图。'} for c in categories}
        with self.lock:
            for category in categories:
                value = self._read(category)
                if category in self.active or value['status'] == 'succeeded':
                    continue
                if value['status'] == 'failed' and not retry:
                    continue
                handle = self.path(category, 'lock').open('a')
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    continue
                self.file_locks[category] = handle
                self.active.add(category)
                self._write(category, {'status': 'queued', 'task_id': value.get('task_id'), 'remote_url': value.get('remote_url')})
                self.pool.submit(self._generate, category, value.get('task_id'), value.get('remote_url'))
        return self.statuses(categories)

    @staticmethod
    def _check_response(response):
        if response.status_code != 200:
            message = {401: '图片服务密钥无效，请检查配置。', 403: '图片服务拒绝请求，请检查密钥权限。',
                       402: '图片服务余额不足。', 429: '图片服务繁忙，请稍后重试。'}.get(response.status_code, '图片服务暂时不可用，请稍后重试。')
            raise ImageError(message)
        value = response.json()
        if not isinstance(value, dict):
            raise ImageError('图片服务返回格式异常。')
        return value

    def _download(self, url):
        # URLs come from the provider, but must never target local/private services.
        for _ in range(4):
            parsed = urlparse(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise ImageError('图片下载地址无效。')
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
            trusted_cdn = parsed.hostname.endswith('.aitohumanize.com') or parsed.hostname in set(os.getenv('IMAGE_CDN_HOSTS', '').split(','))
            fake_ip_range = ipaddress.ip_network('198.18.0.0/15')
            def allowed(address):
                ip = ipaddress.ip_address(address)
                # Clash-style Fake-IP DNS requires the proxy to resolve the real CDN.
                return ip.is_global or (trusted_cdn and ip in fake_ip_range)
            if not addresses or any(not allowed(item[4][0]) for item in addresses):
                raise ImageError('图片下载地址不可用，请检查代理 DNS 或图片 CDN 配置。')
            with requests.get(url, timeout=(10, 60), stream=True, allow_redirects=False) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url = urljoin(url, response.headers.get('Location', ''))
                    continue
                if response.status_code != 200:
                    raise ImageError('生成成功，但图片下载失败，请重试。')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 15 * 1024 * 1024:
                        raise ImageError('图片文件过大。')
                    chunks.append(chunk)
                content = b''.join(chunks)
                if not (content.startswith(b'\x89PNG\r\n\x1a\n') or content.startswith(b'\xff\xd8\xff') or (content.startswith(b'RIFF') and content[8:12] == b'WEBP')):
                    raise ImageError('图片服务返回了无法显示的图片。')
                return content
        raise ImageError('图片下载跳转异常。')

    def _generate(self, category, task_id=None, remote_url=None):
        try:
            self._write(category, {'status': 'running', 'task_id': task_id, 'remote_url': remote_url})
            headers = {'Authorization': f'Bearer {self.key}'}
            if remote_url:
                value = {'status': 'succeeded', 'results': [{'url': remote_url}]}
            elif task_id:
                value = {'id': task_id, 'status': 'running'}
            else:
                prompt = ('Create a beautiful cozy editorial illustration of ' + ACTIVITIES[category] +
                          '. Soft watercolor and gouache, warm cream background, muted sage green and honey beige, '
                          'gentle natural light, calm comforting mood, tasteful composition, no words, no letters, '
                          'no logos, no medical claims. Square composition with generous negative space.')
                if self.gender == 'neutral' or category not in PERSON_ACTIVITIES:
                    prompt += ' IMPORTANT: depict this activity through objects and surroundings only, no people, human faces or human bodies in the image.'
                elif self.gender:
                    prompt += ' IMPORTANT: if people are depicted, show only an adult '+('man' if self.gender=='male' else 'woman')+'; do not depict people of another gender. Do not stereotype activity choices.'
                value = self._check_response(requests.post(self.base + '/v1/api/generate', headers=headers,
                    json={'model': self.model, 'prompt': prompt, 'images': [], 'aspectRatio': '1024x1024',
                          'quality': 'auto', 'replyType': 'json'}, timeout=(10, 180)))
            task_id = value.get('id') or task_id
            deadline = time.monotonic() + 600
            while value.get('status') != 'succeeded':
                task_id = value.get('id') or task_id
                if value.get('status') in ('failed', 'error', 'cancelled'):
                    task_id = None
                    raise ImageError('图片生成失败，请稍后重试。')
                if not isinstance(task_id, str) or not task_id:
                    raise ImageError('图片服务未返回有效任务，请检查模型与接口配置。')
                self._write(category, {'status': 'running', 'task_id': task_id})
                if time.monotonic() >= deadline:
                    raise ImageError('配图仍未生成完成，请稍后点击重试查询。')
                time.sleep(4)
                response = requests.get(self.base + '/v1/api/result', headers=headers,
                                        params={'id': task_id}, timeout=(10, 60))
                if response.status_code == 404:
                    task_id = None
                    raise ImageError('图片任务已过期，请点击重试重新生成。')
                value = self._check_response(response)
            results = value.get('results')
            if not isinstance(results, list) or not results or not isinstance(results[0], dict):
                raise ImageError('图片服务没有返回图片。')
            remote_url = results[0].get('url', '')
            self._write(category, {'status': 'running', 'task_id': task_id, 'remote_url': remote_url})
            content = self._download(remote_url)
            temporary = self.path(category, 'part')
            temporary.write_bytes(content)
            temporary.replace(self.path(category, 'image'))
            self._write(category, {'status': 'succeeded', 'task_id': task_id, 'remote_url': remote_url})
        except ImageError as error:
            self._write(category, {'status': 'failed', 'error': str(error), 'task_id': task_id, 'remote_url': remote_url})
        except requests.RequestException:
            self._write(category, {'status': 'failed', 'error': '图片服务连接超时或网络异常，请重试。', 'task_id': task_id, 'remote_url': remote_url})
        except (ValueError, TypeError, KeyError, OSError):
            # Never forward provider response bodies or credentials to the browser.
            self._write(category, {'status': 'failed', 'error': '配图生成或下载失败，请检查图片服务配置后重试。', 'task_id': task_id, 'remote_url': remote_url})
        finally:
            with self.lock:
                self.active.discard(category)
                handle = self.file_locks.pop(category, None)
                if handle:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                    handle.close()
