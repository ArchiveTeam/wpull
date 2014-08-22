var system = require('system');
var page = require('webpage').create();
var defaultPageSettings = null;
var defaultPageHeaders = {};
var rewriteEnabled = false;

// Begin polling for RPC calls
function readRpc() {
	console.log('Read RPC loop.');

	if (system.stdin.atEnd()) {
		console.log('Stdin at end.');
		setTimeout(readRpc, 100);
		return;
	}

	var line = system.stdin.readLine();

	if (line.slice(0, 5) != '!RPC!') {
		console.log('Ignore unknown start flags.', line);
		setTimeout(readRpc, 100);
		return;
	}

	var rpcInfo = JSON.parse(line.slice(5));
	var replyRpcInfo = {
		'id' : String(Math.random()),
		'reply_id' : rpcInfo['id'],
	};

	try {
		var resultValue = rpcEval(rpcInfo);
		replyRpcInfo['result'] = resultValue;
	} catch (error) {
		replyRpcInfo['error'] = error;
		replyRpcInfo['error_message'] = error.message;
	}

	sendMessage(replyRpcInfo);
	console.log('Replied.');
	setTimeout(readRpc, 1);
}

// Serialize and send
function sendMessage(rpcInfo) {
	var message = JSON.stringify(rpcInfo);
	var chunks = message.match(/.{1,4096}/g);

	if (chunks.length === 1) {
		system.stdout.write('!RPC!');
		system.stdout.writeLine(message);
	} else {
		for (var i = 0; i < chunks.length; i++) {
			if (i === 0) {
				system.stdout.write('!RPC[');
			} else {
				system.stdout.write('!RPC+');
			}
			system.stdout.writeLine(chunks[i]);
		}
		system.stdout.writeLine('!RPC]');
	}

	system.stdout.flush();
}

// Evaluate the RPC.
function rpcEval(rpcInfo) {
	var action = rpcInfo['action'];

	if (action == 'call') {
		console.debug('Call', rpcInfo['name'], rpcInfo['args'],
				rpcInfo['args'].length);

		return callFunction(rpcInfo['name'], rpcInfo['args']);
	} else if (action == 'set') {
		console.debug('Set', rpcInfo['name'], rpcInfo['value']);

		globalEval(rpcInfo['name'] + '=' + JSON.stringify(rpcInfo['value']));
	} else if (action == 'eval') {
		console.debug('Eval', rpcInfo['text']);

		return globalEval(rpcInfo['text']);
	}
}

// Globally evaluate the text.
function globalEval(text) {
	return eval.call(null, text);
}

// Call a function preserving "this"
function callFunction(functionName, functionArgs) {
	var func = globalEval(functionName);
	var owner = null;
	var dotIndex = functionName.lastIndexOf('.');

	if (dotIndex > 0) {
		var ownerName = functionName.slice(0, dotIndex);
		owner = globalEval(ownerName);
	}

	return func.apply(owner, functionArgs);
}

// Return the message itself.
function debugEcho(message) {
	return message;
}

// Attaches the RPC event handlers to the page.
function setupEvents() {
	page.onAlert = function(msg) {
		sendRpcEvent('alert', {
			'message' : msg
		});
	};

	page.onClosing = function(closingPage) {
		sendRpcEvent('closing');
	};

	page.onConfirm = function(msg) {
		sendRpcEvent('confirm', {
			'message' : msg
		});
	};

	page.onConsoleMessage = function(msg, lineNum, sourceId) {
		sendRpcEvent('console_message', {
			'message' : msg,
			'line_num' : lineNum,
			'source_id' : sourceId
		});
	};

	page.onFilePicker = function(oldFile) {
		sendRpcEvent('file_picker', {
			'old_file' : oldFile
		});
	};

	page.onError = function(msg, trace) {
		sendRpcEvent('error', {
			'message' : msg,
			'trace' : trace
		});
	};

	page.onInitialized = function() {
		sendRpcEvent('initialized');
	};

	page.onLoadFinished = function(status) {
		sendRpcEvent('load_finished', {
			'status' : status
		});
	};

	page.onLoadStarted = function() {
		sendRpcEvent('load_started');
	};

	page.onNavigationRequested = function(url, type, willNavigate, main) {
		sendRpcEvent('navigation_requested', {
			'url' : url,
			'type' : type,
			'will_navigate' : willNavigate,
			'main' : main
		});
	};

	page.onPageCreated = function(newPage) {
		sendRpcEvent('page_created');
	};

	page.onPrompt = function(msg, defaultVal) {
		sendRpcEvent('prompt', {
			'message' : msg,
			'default_value' : defaultVal
		});
	};

	page.onResourceError = function(resourceError) {
		sendRpcEvent('resource_error', {
			'resource_error' : resourceError
		});
	};

	page.onResourceReceived = function(response) {
		sendRpcEvent('resource_received', {
			'response' : response
		});
	};

	page.onResourceRequested = function(requestData, networkRequest) {
		sendRpcEvent('resource_requested', {
			'request_data' : requestData,
			'network_request' : networkRequest
		});

		if (!rewriteEnabled) {
			return;
		}

		var url = requestData['url'];

		if (url.indexOf('https://') !== 0) {
			return;
		}

		// TODO: Despite the documentation, can't use this yet:
		// networkRequest.setHeader('X-Wpull-Orig-Url', url);

		// Oh yeah!
		networkRequest.changeUrl(url.replace('https://', 'http://')
				+ '/WPULLHTTPS');
	};

	page.onUrlChanged = function(targetUrl) {
		sendRpcEvent('url_changed', {
			'target_url' : targetUrl
		});
	};
}

// Send RPC event
function sendRpcEvent(eventName, info) {
	var rpcInfo = {
		'id' : String(Math.random()),
		'event' : eventName,
	}

	for (name in info || {}) {
		rpcInfo[name] = info[name];
	}

	sendMessage(rpcInfo);
}

// Set the default page settings
function setDefaultPageSettings(settings) {
	defaultPageSettings = settings;
	applyDefaultPageSettings(settings);
}

// Set the default page headers
function setDefaultPageHeaders(headers) {
	defaultPageHeaders = headers;
	page.customHeaders = headers;
}

// Apply the default page settings
function applyDefaultPageSettings() {
	if (!defaultPageSettings) {
		return;
	}

	for (name in defaultPageSettings) {
		page.settings[name] = defaultPageSettings[name];
	}
}

// Close, create a new page, and setup event handlers.
function resetPage() {
	page.close();
	page = require('webpage').create();
	setupEvents();
	applyDefaultPageSettings();
	page.customHeaders = defaultPageHeaders;
}

var EVENT_SELECTORS = [ '[onload]', '[onunload]', '[onabortonclick]',
		'[ondblclick]', '[onmousedown]', '[onmousemove]', '[onmouseout]',
		'[onmouseover]', '[onmouseup]', '[onkeydown]', '[onkeypress]',
		'[onkeyup]' ].join(' ');

// Return whether the page has script elements or HTML event attributes
function isPageDynamic() {
	var result = page.evaluate(function() {
		return document.getElementsByTagName('script').length
				|| document.querySelector(EVENT_SELECTORS);
	});

	if (result) {
		return true;
	}
}

console.log('Script starting up.')
setupEvents();
readRpc();
