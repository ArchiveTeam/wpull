var system = require('system');

if (system.args.length !== 2) {
	console.log('Argument error.');
	phantom.exit(1);
}

var page = require('webpage').create();
var host_port = system.args[1];

var connection = new WebSocket('ws://localhost:' + host_port);
console.log('Created websocket', connection)

connection.onopen = function(event) {
	console.log('WebSocket ready', event);
};

connection.onerror = function(event) {
	console.log('WebSocket error', event);
};

connection.onmessage = function(event) {
	console.log('WebSocket message');

	var rpc_info = JSON.parse(event.data);
	var reply_rpc_info = {
		'id' : String(Math.random()),
		'reply_id' : rpc_info['id'],
	};

	try {
		var result_value = rpc_eval(rpc_info);
		reply_rpc_info['result'] = result_value;
	} catch (error) {
		reply_rpc_info['error'] = error;
		reply_rpc_info['error_message'] = error.message;
	}

	connection.send(JSON.stringify(reply_rpc_info))
}

// Evaluate the RPC.
// Object => anything
function rpc_eval(rpc_info) {
	var action = rpc_info['action'];

	if (action == 'call') {
		console.debug('Call', rpc_info['name'], rpc_info['args']);

		return global_eval(rpc_info['name']).apply(this, rpc_info['args']);
	} else if (action == 'set') {
		console.debug('Set', rpc_info['name'], rpc_info['value']);

		global_eval(rpc_info['name'] + '=' + rpc_info['value']);
	} else if (action == 'eval') {
		console.debug('Eval', rpc_info['text']);

		return global_eval(rpc_info['text']);
	}
}

// Globally evaluate the text.
// String => anything
function global_eval(text) {
	return eval.call(this, text);
}

// Return the message itself.
function debug_echo(message) {
	return message;
}