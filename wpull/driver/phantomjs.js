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
	this.pageLoaded = false;
	this.pendingResourcesAfterLoad = 0;
	this.activityCounter = 0;
	this.system = require("system");
	this.webpage = require("webpage");
	this.phantom = phantom;
	this.fs = require("fs");
};
PhantomJS.__name__ = true;
PhantomJS.main = function() {
	var app = new PhantomJS();
	app.run();
};
PhantomJS.prototype = {
	logStderrLine: function(message) {
		if(this.system.stderr != null) return this.system.stderr.writeLine(message); else return this.system.stdout.writeLine(message);
	}
	,run: function() {
		this.setUpErrorHandler();
		this.loadConfig();
		this.createPage();
		this.listenPageEvents();
		this.loadUrl();
	}
	,setUpErrorHandler: function() {
		var _g = this;
		this.phantom.onError = function(message,traceArray) {
			_g.logStderrLine(message);
			var _g1 = 0;
			while(_g1 < traceArray.length) {
				var traceLine = traceArray[_g1];
				++_g1;
				var source;
				var functionName = "";
				if(traceLine.file != null) source = traceLine.file; else source = traceLine.sourceURL;
				if(Reflect.field(traceLine,"function") != null) functionName = Reflect.field(traceLine,"function");
				_g.logStderrLine("  " + source + ":" + Std.string(traceLine.line) + " " + functionName);
			}
		};
	}
	,loadConfig: function() {
		if(this.system.args.length != 2) throw "Missing launch configuration.";
		var configContent = this.fs.read(this.system.args[1]);
		this.config = JSON.parse(configContent);
		this.openLogFiles();
	}
	,openLogFiles: function() {
		var eventLogFilename = Reflect.field(this.config,"event_log_filename");
		var actionLogFilename = Reflect.field(this.config,"action_log_filename");
		if(eventLogFilename != null) this.eventLogFile = this.fs.open(eventLogFilename,"w");
		if(actionLogFilename != null) this.actionLogFile = this.fs.open(actionLogFilename,"w");
	}
	,createPage: function() {
		this.page = this.webpage.create();
		this.page.evaluate("function () { document.body.bgColor = 'white'; }");
		this.page.viewportSize = { width : Reflect.field(this.config,"viewport_width"), height : Reflect.field(this.config,"viewport_height")};
		var paperWidth = Reflect.field(this.config,"paper_width");
		var paperHeight = Reflect.field(this.config,"paper_height");
		this.page.paperSize = { width : "" + paperWidth + " px", height : "" + paperHeight + " px", border : "0px"};
		this.page.customHeaders = Reflect.field(this.config,"custom_headers");
		var settings = Reflect.field(this.config,"page_settings");
		var _g = 0;
		var _g1 = Reflect.fields(settings);
		while(_g < _g1.length) {
			var name = _g1[_g];
			++_g;
			Reflect.setField(this.page.settings,name,Reflect.field(settings,name));
		}
	}
	,listenPageEvents: function() {
		var _g = this;
		this.page.onAlert = function(message) {
			_g.logEvent("alert",{ message : message});
		};
		this.page.onClosing = function(closingPage) {
			_g.logEvent("closing");
		};
		this.page.onConfirm = function(message1) {
			_g.logEvent("confirm",{ message : message1});
			return false;
		};
		this.page.onConsoleMessage = function(message2,lineNum,sourceId) {
			_g.logEvent("console_message",{ message : message2, line_num : lineNum, source_id : sourceId});
		};
		this.page.onError = function(message3,trace) {
			_g.logEvent("error",{ message : message3, trace : trace});
		};
		this.page.onFilePicker = function(oldFile) {
			_g.logEvent("file_picker",{ old_file : oldFile});
			return null;
		};
		this.page.onInitialized = function() {
			_g.logEvent("initialized");
		};
		this.page.onLoadFinished = function(status) {
			_g.logEvent("load_finished",{ status : status});
			_g.activityCounter += 1;
		};
		this.page.onLoadStarted = function() {
			_g.logEvent("load_started");
			_g.activityCounter += 1;
		};
		this.page.onNavigationRequested = function(url,type,willNavigate,main) {
			_g.logEvent("navigation_requested",{ url : url, type : type, will_navigate : willNavigate, main : main});
		};
		this.page.onPageCreated = function(newPage) {
			_g.logEvent("page_created",{ });
		};
		this.page.onPrompt = function(message4,defaultValue) {
			_g.logEvent("prompt",{ message : message4, default_value : defaultValue});
			return null;
		};
		this.page.onResourceError = function(resourceError) {
			_g.logEvent("resource_error",{ resource_error : resourceError});
			_g.activityCounter += 1;
			if(_g.pageLoaded) _g.pendingResourcesAfterLoad -= 1;
		};
		this.page.onResourceReceived = function(response) {
			_g.logEvent("resource_received",{ response : response});
			_g.activityCounter += 1;
			if(_g.pageLoaded && response.stage == "end") _g.pendingResourcesAfterLoad -= 1;
		};
		this.page.onResourceRequested = function(requestData,networkRequest) {
			_g.logEvent("resource_requested",{ request_data : requestData, network_request : networkRequest});
			_g.activityCounter += 1;
			if(_g.pageLoaded) _g.pendingResourcesAfterLoad += 1;
		};
		this.page.onResourceTimeout = function(request) {
			_g.logEvent("resource_timeout",{ request : request});
			_g.activityCounter += 1;
			if(_g.pageLoaded) _g.pendingResourcesAfterLoad -= 1;
		};
		this.page.onUrlChanged = function(targetUrl) {
			_g.logEvent("url_changed",{ target_url : targetUrl});
		};
	}
	,logEvent: function(eventName,eventData) {
		if(this.eventLogFile == null) return;
		var line = JSON.stringify({ timestamp : new Date().getTime() / 1000.0, event : eventName, value : eventData});
		this.eventLogFile.write(line);
		this.eventLogFile.write("\n");
	}
	,logAction: function(eventName,eventData) {
		if(this.actionLogFile == null) return;
		var line = JSON.stringify({ timestamp : new Date().getTime() / 1000.0, event : eventName, value : eventData});
		this.actionLogFile.write(line);
		this.actionLogFile.write("\n");
	}
	,loadUrl: function() {
		var _g = this;
		var url = Reflect.field(this.config,"url");
		console.log("Load URL " + url + ".");
		this.page.open(url,function(status) {
			console.log("Page loaded! " + status + ".");
			_g.pageLoaded = true;
		});
		this.pollPageLoad();
	}
	,pollPageLoad: function() {
		console.log("Polling for load.");
		if(this.pageLoaded) this.loadFinishedCallback(); else window.setTimeout($bind(this,this.pollPageLoad),100);
	}
	,loadFinishedCallback: function() {
		console.log("Load finished.");
		if(this.isPageDynamic()) this.scrollPage(); else this.loadFinishedCallback2();
	}
	,loadFinishedCallback2: function() {
		if(Reflect.field(this.config,"snapshot")) this.makeSnapshots();
		this.close();
	}
	,isPageDynamic: function() {
		var result = this.page.evaluate("\n            function () {\n            return document.getElementsByTagName('script').length ||\n                document.querySelector(\n                    '[onload],[onunload],[onabortonclick],[ondblclick],' +\n                    '[onmousedown],[onmousemove],[onmouseout],[onmouseover],' +\n                    '[onmouseup],[onkeydown],[onkeypress],[onkeyup]');\n            }\n        ");
		return result;
	}
	,getPageContentHeight: function() {
		return this.page.evaluate("function() { return document.body.scrollHeight; }");
	}
	,scrollPage: function() {
		var _g = this;
		var currentY = 0;
		var scrollDelay;
		scrollDelay = js.Boot.__cast(Reflect.field(this.config,"wait_time") * 1000 , Int);
		var numScrolls = Reflect.field(this.config,"num_scrolls");
		var smartScroll = Reflect.field(this.config,"smart_scroll");
		var startDate = null;
		var clickX = this.page.viewportSize.width;
		var clickY = this.page.viewportSize.height;
		this.logAction("click",[clickX,clickY]);
		this.sendClick(clickX,clickY);
		var pollForPendingLoad;
		var pollForPendingLoad1 = null;
		pollForPendingLoad1 = function() {
			if(startDate == null) startDate = new Date();
			var duration = new Date().getTime() - startDate.getTime();
			console.log("pendingResourcesAfterLoad=" + _g.pendingResourcesAfterLoad);
			if(_g.pendingResourcesAfterLoad > 0 && duration < 60000) window.setTimeout(pollForPendingLoad1,100); else _g.loadFinishedCallback2();
		};
		pollForPendingLoad = pollForPendingLoad1;
		var cleanupScroll = function() {
			_g.logAction("set_scroll_left",0);
			_g.logAction("set_scroll_top",0);
			_g.setPagePosition(0,0);
			_g.sendKey(_g.page.event.key.Home);
			pollForPendingLoad();
		};
		var actualScroll;
		var actualScroll1 = null;
		actualScroll1 = function() {
			var beforeActivityCount = _g.activityCounter;
			currentY += 768;
			console.log("Scroll page " + currentY + ". numScrolls=" + numScrolls + ".");
			_g.logAction("set_scroll_left",0);
			_g.logAction("set_scroll_top",currentY);
			_g.setPagePosition(0,currentY);
			_g.sendKey(_g.page.event.key.PageDown);
			window.setTimeout(function() {
				var pageHeight = _g.getPageContentHeight();
				if(pageHeight == null) pageHeight = 0;
				console.log("before=" + beforeActivityCount + " activityCounter=" + _g.activityCounter);
				console.log("currentY=" + currentY + " pageHeight=" + pageHeight);
				if(smartScroll && beforeActivityCount == _g.activityCounter && currentY >= pageHeight) {
					cleanupScroll();
					return;
				}
				numScrolls -= 1;
				if(numScrolls > 0) actualScroll1(); else cleanupScroll();
			},scrollDelay);
		};
		actualScroll = actualScroll1;
		actualScroll();
	}
	,setPagePosition: function(x,y) {
		this.page.scrollPosition = { left : x, top : y};
		this.page.evaluate("\n            function () {\n                if (window) {\n                    window.scrollTo(" + x + ", " + y + ");\n                }\n            }\n        ");
	}
	,sendClick: function(x,y,button) {
		if(button == null) button = "left";
		this.page.sendEvent("mousedown",x,y,button);
		this.page.sendEvent("mouseup",x,y,button);
		this.page.sendEvent("click",x,y,button);
	}
	,sendKey: function(key,modifier) {
		if(modifier == null) modifier = 0;
		this.page.sendEvent("keypress",key,null,null,modifier);
		this.page.sendEvent("keydown",key,null,null,modifier);
		this.page.sendEvent("keyup",key,null,null,modifier);
	}
	,makeSnapshots: function() {
		var paths = Reflect.field(this.config,"snapshot_paths");
		var _g = 0;
		while(_g < paths.length) {
			var path = paths[_g];
			++_g;
			console.log("Making snapshot " + path);
			this.renderPage(path);
		}
	}
	,renderPage: function(path) {
		if(StringTools.endsWith(path,".html")) {
			var file = this.fs.open(path,"w");
			file.write(this.page.content);
			file.close();
		} else this.page.render(path);
	}
	,close: function() {
		console.log("Closing.");
		this.page.close();
		if(this.actionLogFile != null) this.actionLogFile.flush();
		if(this.eventLogFile != null) this.eventLogFile.flush();
		this.phantom.exit();
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
Date.prototype.__class__ = Date;
Date.__name__ = ["Date"];
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
