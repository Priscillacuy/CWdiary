import base64
from unittest.mock import Mock

from image_service import ImageService
from test_app import auth, app

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def test_generate_poll_cache_and_auth(app, monkeypatch):
    service = app.extensions['activity_images']
    service.key = 'test-image-secret'
    monkeypatch.setattr(service, '_download', lambda url: PNG)
    post = Mock(return_value=Mock(status_code=200, json=lambda: {'id': 'test-task', 'status': 'running'}))
    get = Mock(return_value=Mock(status_code=200, json=lambda: {'id': 'test-task', 'status': 'succeeded', 'results': [{'url': 'https://cdn.example/image.png'}]}))
    monkeypatch.setattr('image_service.requests.post', post)
    monkeypatch.setattr('image_service.requests.get', get)
    c = app.test_client()
    assert c.get('/api/activity-images?categories=yoga').status_code == 401
    assert c.get('/api/activity-images/yoga/file').status_code == 401
    h = auth(c)
    assert c.post('/api/activity-images', headers=h, json={'categories': ['../../secret']}).status_code == 400
    assert c.post('/api/activity-images', headers=h, json={'categories': ['yoga']}).status_code == 200
    service.pool.shutdown(wait=True)
    result = c.get('/api/activity-images?categories=yoga').json
    assert result['images']['yoga']['status'] == 'succeeded'
    assert 'task_id' not in str(result)
    file = c.get(result['images']['yoga']['url'])
    assert file.status_code == 200 and file.data == PNG
    assert file.content_type == 'image/png'
    assert c.post('/api/activity-images', headers=h, json={'categories': ['yoga']}).status_code == 200
    assert post.call_count == 1
    request = post.call_args.kwargs
    assert request['json']['model'] == 'gpt-image-2.6'
    assert request['json']['images'] == []
    assert 'diary' not in request['json']['prompt']
    assert get.call_args.kwargs['params'] == {'id': 'test-task'}


def test_provider_error_no_secret_and_retry(app, monkeypatch):
    service = app.extensions['activity_images']
    service.key = 'do-not-expose-test-secret'
    post = Mock(return_value=Mock(status_code=401))
    monkeypatch.setattr('image_service.requests.post', post)
    service.start(['music'])
    service.pool.shutdown(wait=True)
    value = service.statuses(['music'])['music']
    assert value['status'] == 'failed'
    assert '密钥无效' in value['error']
    assert service.key not in str(value)
    service.start(['music'])
    assert post.call_count == 1  # Failed requests do not retry or charge automatically.
    monkeypatch.setattr(service.pool, 'submit', Mock())
    service.start(['music'], retry=True)
    assert service.pool.submit.call_count == 1


def test_missing_key_and_interrupted_job(tmp_path, monkeypatch):
    monkeypatch.delenv('IMAGE_API_KEY', raising=False)
    service = ImageService(tmp_path)
    assert service.start(['meal'])['meal']['status'] == 'unconfigured'
    service._write('meal', {'status': 'running', 'task_id': 'old-task'})
    value = service.statuses(['meal'])['meal']
    assert value['status'] == 'failed'
    assert 'task_id' not in value
    service.pool.shutdown(wait=True)


def test_download_retry_reuses_generated_result(tmp_path, monkeypatch):
    service = ImageService(tmp_path)
    service.key = 'test-key'
    service._write('yoga', {'status': 'failed', 'remote_url': 'https://cdn.example/yoga.png', 'task_id': 'already-paid-task'})
    post = Mock()
    monkeypatch.setattr('image_service.requests.post', post)
    download = Mock(return_value=PNG)
    monkeypatch.setattr(service, '_download', download)
    service.start(['yoga'], retry=True)
    service.pool.shutdown(wait=True)
    assert service.statuses(['yoga'])['yoga']['status'] == 'succeeded'
    assert post.call_count == 0
    download.assert_called_once_with('https://cdn.example/yoga.png')


def test_download_blocks_private_hosts(tmp_path, monkeypatch):
    import pytest
    from image_service import ImageError
    service = ImageService(tmp_path)
    monkeypatch.setattr('image_service.socket.getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))])
    get = Mock()
    monkeypatch.setattr('image_service.requests.get', get)
    with pytest.raises(ImageError):
        service._download('https://localhost/private')
    assert get.call_count == 0
    service.pool.shutdown(wait=True)


def test_proxy_fake_ip_allowed_only_for_provider_cdn(tmp_path, monkeypatch):
    import pytest
    from unittest.mock import MagicMock
    from image_service import ImageError
    service = ImageService(tmp_path)
    monkeypatch.setattr('image_service.socket.getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('198.18.0.195', 443))])
    response = MagicMock(status_code=200, is_redirect=False)
    response.__enter__.return_value = response
    response.iter_content.return_value = [PNG]
    get = Mock(return_value=response)
    monkeypatch.setattr('image_service.requests.get', get)
    assert service._download('https://file5.aitohumanize.com/generated.png') == PNG
    assert 'headers' not in get.call_args.kwargs  # Image API credentials never go to the CDN.
    with pytest.raises(ImageError):
        service._download('https://untrusted.example/private')
    with pytest.raises(ImageError):
        service._download('https://aitohumanize.com.untrusted.example/private')
    assert get.call_count == 1
    service.pool.shutdown(wait=True)


def test_expired_task_can_be_regenerated(tmp_path, monkeypatch):
    service = ImageService(tmp_path)
    service.key = 'test-key'
    service._write('music', {'status': 'failed', 'task_id': 'expired-task'})
    monkeypatch.setattr('image_service.time.sleep', lambda _: None)
    monkeypatch.setattr('image_service.requests.get', Mock(return_value=Mock(status_code=404)))
    service.start(['music'], retry=True)
    service.pool.shutdown(wait=True)
    value = service._read('music')
    assert value['status'] == 'failed'
    assert value['task_id'] is None
    assert '过期' in value['error']


def test_missing_local_file_keeps_download_url(tmp_path):
    service = ImageService(tmp_path)
    service._write('read', {'status': 'succeeded', 'remote_url': 'https://cdn.example/read.png'})
    value = service._read('read')
    assert value['status'] == 'failed'
    assert value['remote_url'] == 'https://cdn.example/read.png'
    assert 'remote_url' not in service.statuses(['read'])['read']
    service.pool.shutdown(wait=True)


def test_batch_and_frontend_do_not_duplicate_image_jobs(tmp_path, monkeypatch):
    first, second = ImageService(tmp_path), ImageService(tmp_path)
    first.key = second.key = 'test-key'
    first_submit, second_submit = Mock(), Mock()
    monkeypatch.setattr(first.pool, 'submit', first_submit)
    monkeypatch.setattr(second.pool, 'submit', second_submit)
    first.start(['natural_breath'])
    result = second.start(['natural_breath'])
    assert first_submit.call_count == 1
    assert second_submit.call_count == 0
    assert result['natural_breath']['status'] == 'queued'
    first.file_locks.pop('natural_breath').close()
    first.active.clear()
    first.pool.shutdown(wait=True)
    second.pool.shutdown(wait=True)
