local injected_url_found = false

wpull_hook.callbacks.resolve_dns = function(host)
  --  print('resolve_dns', host)
  assert(host == 'localhost')
  return '127.0.0.1'
end

wpull_hook.callbacks.accept_url = function(url_info, record_info, verdict, reasons)
  --  print('accept_url', url_info)
  assert(url_info['url'])
  local accepted_paths = {
    ['/robots.txt'] = true,
    ['/'] = true,
    ['/post/'] = true,
    ['/%95%B6%8E%9A%89%BB%82%AF/'] = true,
    ['/static/style.css'] = true,
  }
  assert(accepted_paths[url_info['path']])
  assert(record_info['url'])
  assert(reasons['filters']['HTTPFilter'])

  for name, passed in pairs(reasons.filters) do
    assert(name)
  end

  if url_info['path'] == '/' then
    assert(not record_info['inline'])
    assert(verdict)
  elseif url_info['path'] == '/post/' then
    assert(not verdict)
    verdict = true
  elseif url_info['path'] == '/style.css' then
    assert(record_info['inline'])
  elseif url_info['path'] == '/robots.txt' then
    verdict = false
  end

  return verdict
end

wpull_hook.callbacks.handle_response = function(url_info, http_info)
  --  print('handle_response', url_info)

  if url_info['path'] == '/' then
    assert(http_info['status_code'] == 200)
    assert(http_info.body['content_size'])
  elseif url_info['path'] == '/post/' then
    assert(http_info['status_code'] == 200)
    injected_url_found = true
    return wpull_hook.actions.FINISH
  end

  return wpull_hook.actions.NORMAL
end

wpull_hook.callbacks.handle_error = function(url_info, error_info)
  --  print('handle_response', url_info, error)
  assert(error_info['error'])
  return wpull_hook.actions.NORMAL
end

wpull_hook.callbacks.get_urls = function(filename, url_info, document_info)
  --  print('get_urls', filename)
  assert(filename)
  local file = io.open(filename, 'r')
  assert(file)
  assert(url_info['url'])

  if url_info['path'] == '/' then
    local url_table = {}
    table.insert(url_table,
      {
        ['url'] = 'http://localhost:'..url_info['port']..'/post/',
        ['inline'] = true,
        ['post_data'] = 'text=hello',
        ['replace'] = true,
      })
    return url_table
  end

  return nil
end

wpull_hook.callbacks.finish_statistics = function(start_time, end_time, num_urls, bytes_downloaded)
  --  print('finish_statistics', start_time)
  assert(start_time)
  assert(end_time)
end

wpull_hook.callbacks.exit_status = function(exit_code)
  --  print('exit_status', exit_code)
  assert(exit_code == 0)
  assert(injected_url_found)
  return 42
end
