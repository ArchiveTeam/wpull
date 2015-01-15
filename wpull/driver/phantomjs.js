(function () { "use strict";
var HxOverrides = function() { };
HxOverrides.__name__ = true;
HxOverrides.substr = function(s,pos,len) {
	if(pos != null && pos != 0 && len != null && len < 0) return "";
	if(len == null) len = s.length;
	if(pos < 0) {
		pos = s.length + pos;
		if(pos < 0) pos = 0;
	} else if(len < 0) len = s.length + len - pos;
	return s.substr(pos,len);
};
var PhantomJS = function() {
	this.system = require("system");
	this.webpage = require("webpage");
	this.phantom = phantom;
	this.fs = require("fs");
	this.pollTimer = setInterval($bind(this,this.pollForCommand),100);
};
PhantomJS.__name__ = true;
PhantomJS.main = function() {
	var app = new PhantomJS();
};
PhantomJS.prototype = {
	pollForCommand: function() {
		this.sendMessage({ event : "poll"});
		var commandMessage = this.readMessage();
		var replyValue = null;
		var _g = commandMessage.command;
		if(_g == null) return; else switch(_g) {
		case "new_page":
			this.newPage();
			break;
		case "open_url":
			this.page.open(commandMessage.url);
			this.listenEvents();
			break;
		case "close_page":
			this.page.close();
			this.page = null;
			break;
		case "set_page_size":
			this.setPageSize(commandMessage.viewport_width,commandMessage.viewport_height,commandMessage.paper_width,commandMessage.paper_height);
			break;
		case "render_page":
			this.renderPage(commandMessage.path);
			break;
		case "set_page_custom_headers":
			this.setPageCustomHeaders(commandMessage.headers);
			break;
		case "set_page_settings":
			this.setPageSettings(commandMessage.settings);
			break;
		case "scroll_page":
			this.scrollPage(commandMessage.x,commandMessage.y);
			break;
		case "exit":
			this.exit(commandMessage.exit_code);
			break;
		case "get_page_url":
			replyValue = this.page.url;
			break;
		case "click":
			this.sendClick(commandMessage.x,commandMessage.y,commandMessage.button);
			break;
		case "key":
			this.sendKey(commandMessage.key,commandMessage.modifier);
			break;
		case "is_page_dynamic":
			replyValue = this.isPageDynamic();
			break;
		default:
			console.log("Unknown command");
		}
		this.sendMessage({ event : "reply", value : replyValue, reply_id : commandMessage.message_id});
	}
	,sendMessage: function(message) {
		var messageString = JSON.stringify(message);
		this.system.stdout.write("!RPC ");
		this.system.stdout.writeLine(messageString);
	}
	,readMessage: function() {
		var messageString = this.system.stdin.readLine();
		var message = JSON.parse(messageString.slice(5));
		return message;
	}
	,sendEvent: function(eventName,args) {
		if(!args) args = { };
		var message = args;
		args.event = eventName;
		this.sendMessage(message);
		var reply = this.readMessage();
		return reply.value;
	}
	,newPage: function() {
		if(this.page) this.closePage();
		this.page = this.webpage.create();
		this.page.evaluate("function () { document.body.bgColor = 'white'; }");
	}
	,closePage: function() {
		this.page.close();
		this.page = null;
	}
	,renderPage: function(path) {
		if(StringTools.endsWith(path,".html")) {
			var file = this.fs.open(path,"w");
			file.write(this.page.content);
			file.close();
		} else this.page.render(path);
	}
	,setPageSize: function(viewportWidth,viewportHeight,paperWidth,paperHeight) {
		this.page.viewportSize = { width : viewportWidth, height : viewportHeight};
		this.page.paperSize = { width : "" + paperWidth + " px", height : "" + paperHeight + " px", border : "0px"};
	}
	,setPageSettings: function(settings) {
		var _g = 0;
		var _g1 = Reflect.fields(settings);
		while(_g < _g1.length) {
			var name = _g1[_g];
			++_g;
			Reflect.setField(this.page.settings,name,Reflect.field(settings,name));
		}
	}
	,setPageCustomHeaders: function(headers) {
		this.page.customHeaders = headers;
	}
	,scrollPage: function(x,y) {
		this.page.scrollPosition = { left : x, top : y};
		this.page.evaluate("\n            function () {\n                if (window) {\n                    window.scrollTo(" + x + ", " + y + ");\n                }\n            }\n        ");
	}
	,sendClick: function(x,y,button) {
		this.page.sendEvent("mousedown",x,y,button);
		this.page.sendEvent("mouseup",x,y,button);
		this.page.sendEvent("click",x,y,button);
	}
	,sendKey: function(key,modifier) {
		this.page.sendEvent("keypress",key,null,null,modifier);
		this.page.sendEvent("keydown",key,null,null,modifier);
		this.page.sendEvent("keyup",key,null,null,modifier);
	}
	,isPageDynamic: function() {
		var result = this.page.evaluate("\n            function () {\n            return document.getElementsByTagName('script').length ||\n                document.querySelector(\n                    '[onload],[onunload],[onabortonclick],[ondblclick],' +\n                    '[onmousedown],[onmousemove],[onmouseout],[onmouseover],' +\n                    '[onmouseup],[onkeydown],[onkeypress],[onkeyup]');\n            }\n        ");
		return result;
	}
	,listenEvents: function() {
		var _g = this;
		this.page.onAlert = function(message) {
			_g.sendEvent("alert",{ message : message});
		};
		this.page.onClosing = function(closingPage) {
			_g.sendEvent("closing");
		};
		this.page.onConfirm = function(message1) {
			return _g.sendEvent("confirm",{ message : message1});
		};
		this.page.onConsoleMessage = function(message2,lineNum,sourceId) {
			_g.sendEvent("console_message",{ message : message2, line_num : lineNum, source_id : sourceId});
		};
		this.page.onFilePicker = function(oldFile) {
			return _g.sendEvent("file_picker",{ old_file : oldFile});
		};
		this.page.onInitialized = function() {
			_g.sendEvent("initialized");
		};
		this.page.onLoadFinished = function(status) {
			_g.sendEvent("load_finished",{ status : status});
		};
		this.page.onLoadStarted = function() {
			_g.sendEvent("load_started");
		};
		this.page.onNavigationRequested = function(url,type,willNavigate,main) {
			_g.sendEvent("navigation_requested",{ url : url, type : type, will_navigate : willNavigate, main : main});
		};
		this.page.onPageCreated = function(newPage) {
			_g.sendEvent("page_created",{ });
		};
		this.page.onPrompt = function(message3,defaultValue) {
			return _g.sendEvent("prompt",{ message : message3, default_value : defaultValue});
		};
		this.page.onResourceError = function(resourceError) {
			_g.sendEvent("resource_error",{ resource_error : resourceError});
		};
		this.page.onResourceReceived = function(response) {
			_g.sendEvent("resource_received",{ response : response});
		};
		this.page.onResourceRequested = function(requestData,networkRequest) {
			var reply = _g.sendEvent("resource_requested",{ request_data : requestData, network_request : networkRequest});
			if(!reply) return;
			if(js.Boot.__cast(reply , String) == "abort") networkRequest.abort(); else if(reply) networkRequest.changeUrl(reply);
		};
		this.page.onResourceTimeout = function(request) {
			_g.sendEvent("resource_timeout",{ request : request});
		};
		this.page.onUrlChanged = function(targetUrl) {
			_g.sendEvent("url_changed",{ target_url : targetUrl});
		};
	}
	,exit: function(exitCode) {
		if(exitCode == null) exitCode = 0;
		if(this.pollTimer) {
			clearTimeout(this.pollTimer);
			this.pollTimer = null;
		}
		this.phantom.exit(exitCode);
	}
	,__class__: PhantomJS
};
var Reflect = function() { };
Reflect.__name__ = true;
Reflect.field = function(o,field) {
	try {
		return o[field];
	} catch( e ) {
		return null;
	}
};
Reflect.setField = function(o,field,value) {
	o[field] = value;
};
Reflect.fields = function(o) {
	var a = [];
	if(o != null) {
		var hasOwnProperty = Object.prototype.hasOwnProperty;
		for( var f in o ) {
		if(f != "__id__" && f != "hx__closures__" && hasOwnProperty.call(o,f)) a.push(f);
		}
	}
	return a;
};
var Std = function() { };
Std.__name__ = true;
Std.string = function(s) {
	return js.Boot.__string_rec(s,"");
};
var StringTools = function() { };
StringTools.__name__ = true;
StringTools.endsWith = function(s,end) {
	var elen = end.length;
	var slen = s.length;
	return slen >= elen && HxOverrides.substr(s,slen - elen,elen) == end;
};
var js = {};
js.Boot = function() { };
js.Boot.__name__ = true;
js.Boot.getClass = function(o) {
	if((o instanceof Array) && o.__enum__ == null) return Array; else return o.__class__;
};
js.Boot.__string_rec = function(o,s) {
	if(o == null) return "null";
	if(s.length >= 5) return "<...>";
	var t = typeof(o);
	if(t == "function" && (o.__name__ || o.__ename__)) t = "object";
	switch(t) {
	case "object":
		if(o instanceof Array) {
			if(o.__enum__) {
				if(o.length == 2) return o[0];
				var str = o[0] + "(";
				s += "\t";
				var _g1 = 2;
				var _g = o.length;
				while(_g1 < _g) {
					var i = _g1++;
					if(i != 2) str += "," + js.Boot.__string_rec(o[i],s); else str += js.Boot.__string_rec(o[i],s);
				}
				return str + ")";
			}
			var l = o.length;
			var i1;
			var str1 = "[";
			s += "\t";
			var _g2 = 0;
			while(_g2 < l) {
				var i2 = _g2++;
				str1 += (i2 > 0?",":"") + js.Boot.__string_rec(o[i2],s);
			}
			str1 += "]";
			return str1;
		}
		var tostr;
		try {
			tostr = o.toString;
		} catch( e ) {
			return "???";
		}
		if(tostr != null && tostr != Object.toString) {
			var s2 = o.toString();
			if(s2 != "[object Object]") return s2;
		}
		var k = null;
		var str2 = "{\n";
		s += "\t";
		var hasp = o.hasOwnProperty != null;
		for( var k in o ) {
		if(hasp && !o.hasOwnProperty(k)) {
			continue;
		}
		if(k == "prototype" || k == "__class__" || k == "__super__" || k == "__interfaces__" || k == "__properties__") {
			continue;
		}
		if(str2.length != 2) str2 += ", \n";
		str2 += s + k + " : " + js.Boot.__string_rec(o[k],s);
		}
		s = s.substring(1);
		str2 += "\n" + s + "}";
		return str2;
	case "function":
		return "<function>";
	case "string":
		return o;
	default:
		return String(o);
	}
};
js.Boot.__interfLoop = function(cc,cl) {
	if(cc == null) return false;
	if(cc == cl) return true;
	var intf = cc.__interfaces__;
	if(intf != null) {
		var _g1 = 0;
		var _g = intf.length;
		while(_g1 < _g) {
			var i = _g1++;
			var i1 = intf[i];
			if(i1 == cl || js.Boot.__interfLoop(i1,cl)) return true;
		}
	}
	return js.Boot.__interfLoop(cc.__super__,cl);
};
js.Boot.__instanceof = function(o,cl) {
	if(cl == null) return false;
	switch(cl) {
	case Int:
		return (o|0) === o;
	case Float:
		return typeof(o) == "number";
	case Bool:
		return typeof(o) == "boolean";
	case String:
		return typeof(o) == "string";
	case Array:
		return (o instanceof Array) && o.__enum__ == null;
	case Dynamic:
		return true;
	default:
		if(o != null) {
			if(typeof(cl) == "function") {
				if(o instanceof cl) return true;
				if(js.Boot.__interfLoop(js.Boot.getClass(o),cl)) return true;
			}
		} else return false;
		if(cl == Class && o.__name__ != null) return true;
		if(cl == Enum && o.__ename__ != null) return true;
		return o.__enum__ == cl;
	}
};
js.Boot.__cast = function(o,t) {
	if(js.Boot.__instanceof(o,t)) return o; else throw "Cannot cast " + Std.string(o) + " to " + Std.string(t);
};
var $_, $fid = 0;
function $bind(o,m) { if( m == null ) return null; if( m.__id__ == null ) m.__id__ = $fid++; var f; if( o.hx__closures__ == null ) o.hx__closures__ = {}; else f = o.hx__closures__[m.__id__]; if( f == null ) { f = function(){ return f.method.apply(f.scope, arguments); }; f.scope = o; f.method = m; o.hx__closures__[m.__id__] = f; } return f; }
String.prototype.__class__ = String;
String.__name__ = true;
Array.__name__ = true;
var Int = { __name__ : ["Int"]};
var Dynamic = { __name__ : ["Dynamic"]};
var Float = Number;
Float.__name__ = ["Float"];
var Bool = Boolean;
Bool.__ename__ = ["Bool"];
var Class = { __name__ : ["Class"]};
var Enum = { };
PhantomJS.main();
})();
