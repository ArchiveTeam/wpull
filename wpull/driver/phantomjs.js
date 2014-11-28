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
Math.__name__ = true;
var PhantomJS = function() {
	this.system = require("system");
	this.webpage = require("webpage");
	this.phantom = phantom;
	this.fs = require("fs");
	this.pollTimer = setInterval($bind(this,this.pollForCommand),100);
};
PhantomJS.__name__ = true;
PhantomJS.main = function() {
	haxe.Log.trace("Hello world",{ fileName : "PhantomJS.hx", lineNumber : 21, className : "PhantomJS", methodName : "main"});
	var app = new PhantomJS();
};
PhantomJS.prototype = {
	pollForCommand: function() {
		this.sendMessage({ event : "poll"});
		var commandMessage = this.readMessage();
		var replyValue = null;
		haxe.Log.trace("pollForCommand",{ fileName : "PhantomJS.hx", lineNumber : 30, className : "PhantomJS", methodName : "pollForCommand", customParams : [commandMessage]});
		var _g = commandMessage.command;
		if(_g == null) {
		} else switch(_g) {
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
		default:
			haxe.Log.trace("Unknown command",{ fileName : "PhantomJS.hx", lineNumber : 60, className : "PhantomJS", methodName : "pollForCommand"});
		}
		this.sendMessage({ event : "reply", value : replyValue});
	}
	,sendMessage: function(message) {
		haxe.Log.trace("send message",{ fileName : "PhantomJS.hx", lineNumber : 67, className : "PhantomJS", methodName : "sendMessage"});
		var messageString = JSON.stringify(message);
		this.system.stdout.write("!RPC ");
		this.system.stdout.writeLine(messageString);
	}
	,readMessage: function() {
		haxe.Log.trace("read message",{ fileName : "PhantomJS.hx", lineNumber : 74, className : "PhantomJS", methodName : "readMessage"});
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
		this.page.sendEvent("keypress",this.page.event.key.PageDown);
		this.page.sendEvent("keydown",this.page.event.key.PageDown);
		this.page.sendEvent("keyup",this.page.event.key.PageDown);
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
		this.page.onError = function(message3,trace) {
			_g.sendEvent("error",{ message : message3, trace : trace});
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
		this.page.onPrompt = function(message4,defaultValue) {
			return _g.sendEvent("prompt",{ message : message4, default_value : defaultValue});
		};
		this.page.onResourceError = function(resourceError) {
			_g.sendEvent("resource_error",{ resource_error : resourceError});
		};
		this.page.onResourceReceived = function(response) {
			_g.sendEvent("resource_received",{ response : response});
		};
		this.page.onResourceRequested = function(requestData,networkRequest) {
			var reply = _g.sendEvent("resource_requested",{ request_data : requestData, network_request : networkRequest});
			var replyType = Type["typeof"](reply);
			if(replyType == ValueType.TBool) networkRequest.abort(); else if(reply) networkRequest.changeUrl(reply);
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
var StringTools = function() { };
StringTools.__name__ = true;
StringTools.endsWith = function(s,end) {
	var elen = end.length;
	var slen = s.length;
	return slen >= elen && HxOverrides.substr(s,slen - elen,elen) == end;
};
var ValueType = { __ename__ : true, __constructs__ : ["TNull","TInt","TFloat","TBool","TObject","TFunction","TClass","TEnum","TUnknown"] };
ValueType.TNull = ["TNull",0];
ValueType.TNull.__enum__ = ValueType;
ValueType.TInt = ["TInt",1];
ValueType.TInt.__enum__ = ValueType;
ValueType.TFloat = ["TFloat",2];
ValueType.TFloat.__enum__ = ValueType;
ValueType.TBool = ["TBool",3];
ValueType.TBool.__enum__ = ValueType;
ValueType.TObject = ["TObject",4];
ValueType.TObject.__enum__ = ValueType;
ValueType.TFunction = ["TFunction",5];
ValueType.TFunction.__enum__ = ValueType;
ValueType.TClass = function(c) { var $x = ["TClass",6,c]; $x.__enum__ = ValueType; return $x; };
ValueType.TEnum = function(e) { var $x = ["TEnum",7,e]; $x.__enum__ = ValueType; return $x; };
ValueType.TUnknown = ["TUnknown",8];
ValueType.TUnknown.__enum__ = ValueType;
var Type = function() { };
Type.__name__ = true;
Type["typeof"] = function(v) {
	var _g = typeof(v);
	switch(_g) {
	case "boolean":
		return ValueType.TBool;
	case "string":
		return ValueType.TClass(String);
	case "number":
		if(Math.ceil(v) == v % 2147483648.0) return ValueType.TInt;
		return ValueType.TFloat;
	case "object":
		if(v == null) return ValueType.TNull;
		var e = v.__enum__;
		if(e != null) return ValueType.TEnum(e);
		var c;
		if((v instanceof Array) && v.__enum__ == null) c = Array; else c = v.__class__;
		if(c != null) return ValueType.TClass(c);
		return ValueType.TObject;
	case "function":
		if(v.__name__ || v.__ename__) return ValueType.TObject;
		return ValueType.TFunction;
	case "undefined":
		return ValueType.TNull;
	default:
		return ValueType.TUnknown;
	}
};
var haxe = {};
haxe.Log = function() { };
haxe.Log.__name__ = true;
haxe.Log.trace = function(v,infos) {
	js.Boot.__trace(v,infos);
};
var js = {};
js.Boot = function() { };
js.Boot.__name__ = true;
js.Boot.__unhtml = function(s) {
	return s.split("&").join("&amp;").split("<").join("&lt;").split(">").join("&gt;");
};
js.Boot.__trace = function(v,i) {
	var msg;
	if(i != null) msg = i.fileName + ":" + i.lineNumber + ": "; else msg = "";
	msg += js.Boot.__string_rec(v,"");
	if(i != null && i.customParams != null) {
		var _g = 0;
		var _g1 = i.customParams;
		while(_g < _g1.length) {
			var v1 = _g1[_g];
			++_g;
			msg += "," + js.Boot.__string_rec(v1,"");
		}
	}
	var d;
	if(typeof(document) != "undefined" && (d = document.getElementById("haxe:trace")) != null) d.innerHTML += js.Boot.__unhtml(msg) + "<br/>"; else if(typeof console != "undefined" && console.log != null) console.log(msg);
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
var $_, $fid = 0;
function $bind(o,m) { if( m == null ) return null; if( m.__id__ == null ) m.__id__ = $fid++; var f; if( o.hx__closures__ == null ) o.hx__closures__ = {}; else f = o.hx__closures__[m.__id__]; if( f == null ) { f = function(){ return f.method.apply(f.scope, arguments); }; f.scope = o; f.method = m; o.hx__closures__[m.__id__] = f; } return f; }
Math.NaN = Number.NaN;
Math.NEGATIVE_INFINITY = Number.NEGATIVE_INFINITY;
Math.POSITIVE_INFINITY = Number.POSITIVE_INFINITY;
Math.isFinite = function(i) {
	return isFinite(i);
};
Math.isNaN = function(i1) {
	return isNaN(i1);
};
String.prototype.__class__ = String;
String.__name__ = true;
Array.__name__ = true;
PhantomJS.main();
})();
