/// <reference path="WinJS.intellisense.js"/>
/// <reference path="WinJS.intellisense-setup.js"/>
(function (){
	WinJS.Namespace.define("OrzPublicWorks.NamingDept.WindowsPhone",{
		submitRequest: WinJS.UI.eventHandler(function (eventArgs){
			var command = eventArgs.currentTarget;
			// TODO: Implement naming dept
		}),
		loaded: false
	});
	
	WinJS.Binding.processAll(null, OrzPublicWorks.NamingDept.WindowsPhone).then(function () {
		WinJS.UI.processAll().done(function () {
			
			var appHeader = document.getElementById("appHeader");
			var titleTextArea = document.getElementById("titleTextArea");
			
			OrzPublicWorks.NamingDept.WindowsPhone.loaded = true;
			WinJS.UI.Animation.enterPage([appHeader,titleTextArea], null);
		});
	});
	
}());