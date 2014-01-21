

wpull_hook.callbacks.resolve_dns = function(host)
--  print('resolve_dns', host)
  assert(host)
  return '127.0.0.1'
end

wpull_hook.callbacks.accept_url = function(url_info, record_info, verdict, reasons)
--  print('accept_url', url_info)
  assert(url_info['url'])
  assert(record_info['url'])
  assert(reasons['filters'])
  return verdict
end

wpull_hook.callbacks.handle_response = function(url_info, http_info)
--  print('handle_response', url_info)
  assert(url_info['url'])
  assert(http_info['status_code'])
  return wpull_hook.actions.NORMAL
end

wpull_hook.callbacks.handle_error = function(url_info, error)
--  print('handle_response', url_info, error)
  assert(error['error'])
  return wpull_hook.actions.NORMAL
end

wpull_hook.callbacks.get_urls = function(filename, url_info, document_info)
--  print('get_urls', filename)
  assert(filename)
  assert(url_info['url'])
  return nil
end

wpull_hook.callbacks.finish_statistics = function(start_time, end_time, num_urls, bytes_downloaded)
--  print('finish_statistics', start_time)
  assert(start_time)
  assert(end_time)
end

wpull_hook.callbacks.exit_status = function(exit_code)
  print('exit_status', exit_code)
  return 42
end
