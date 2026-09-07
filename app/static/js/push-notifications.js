(function(){
"use strict";
window.KSCPushNotifications={
registration:null,
buttons:[],
publicKey:"",
busy:false,
async init(){
if(!("serviceWorker" in navigator)){
console.log("ℹ️ Service workers are not supported.");
this.updateButtons("unsupported");
return false;
}
if(!("PushManager" in window)){
console.log("ℹ️ Push notifications are not supported.");
this.updateButtons("unsupported");
return false;
}
try{
this.registration=await navigator.serviceWorker.register("/service-worker.js");
console.log("✅ KSC service worker registered.");
return true;
}catch(error){
console.error("❌ Service worker registration failed:",error);
this.updateButtons("error");
return false;
}
},
async requestPermission(){
if(!("Notification" in window)){
console.log("ℹ️ Browser notifications are not supported.");
return false;
}
if(Notification.permission==="granted"){
return true;
}
if(Notification.permission==="denied"){
console.log("⚠️ Notification permission has been denied.");
return false;
}
try{
const permission=await Notification.requestPermission();
console.log("🔔 Notification permission:",permission);
return permission==="granted";
}catch(error){
console.error("❌ Notification permission error:",error);
return false;
}
},
urlBase64ToUint8Array(base64String){
if(!base64String){
throw new Error("VAPID public key is missing.");
}
const padding="=".repeat((4-base64String.length%4)%4);
const base64=(base64String+padding).replace(/-/g,"+").replace(/_/g,"/");
const rawData=window.atob(base64);
const outputArray=new Uint8Array(rawData.length);
for(let i=0;i<rawData.length;++i){
outputArray[i]=rawData.charCodeAt(i);
}
return outputArray;
},
getCSRFToken(){
const element=document.querySelector('meta[name="csrf-token"]');
if(element){
return element.getAttribute("content")||"";
}
const input=document.querySelector('input[name="csrf_token"]');
if(input){
return input.value||"";
}
return "";
},
async subscribe(publicKey){
try{
if(!publicKey){
console.error("❌ VAPID public key is missing.");
this.updateButtons("error");
return false;
}
this.publicKey=publicKey;
if(!this.registration){
const initialized=await this.init();
if(!initialized){
return false;
}
}
const permissionGranted=await this.requestPermission();
if(!permissionGranted){
console.log("ℹ️ Notification permission was not granted.");
this.updateButtons("off");
return false;
}
let subscription=await this.registration.pushManager.getSubscription();
if(!subscription){
subscription=await this.registration.pushManager.subscribe({
userVisibleOnly:true,
applicationServerKey:this.urlBase64ToUint8Array(publicKey)
});
console.log("✅ New push subscription created.");
}else{
console.log("ℹ️ Existing push subscription found.");
}
const subscriptionData=subscription.toJSON();
const csrfToken=this.getCSRFToken();
const headers={
"Content-Type":"application/json"
};
if(csrfToken){
headers["X-CSRFToken"]=csrfToken;
}
const response=await fetch("/save-subscription",{
method:"POST",
headers:headers,
credentials:"same-origin",
body:JSON.stringify(subscriptionData)
});
let result={};
try{
result=await response.json();
}catch(error){
console.error("❌ Invalid server response:",error);
}
if(!response.ok||!result.success){
console.error("❌ Failed to save push subscription:",result);
this.updateButtons("off");
return false;
}
console.log("✅ Push subscription saved successfully.");
this.updateButtons("on");
return true;
}catch(error){
console.error("❌ Push subscription error:",error);
this.updateButtons("error");
return false;
}
},
async unsubscribe(){
try{
if(!this.registration){
const initialized=await this.init();
if(!initialized){
return false;
}
}
const subscription=await this.registration.pushManager.getSubscription();
if(!subscription){
console.log("ℹ️ No push subscription exists.");
this.updateButtons("off");
return true;
}
const csrfToken=this.getCSRFToken();
const headers={
"Content-Type":"application/json"
};
if(csrfToken){
headers["X-CSRFToken"]=csrfToken;
}
const response=await fetch("/remove-subscription",{
method:"POST",
headers:headers,
credentials:"same-origin",
body:JSON.stringify({
endpoint:subscription.endpoint
})
});
let result={};
try{
result=await response.json();
}catch(error){
console.error("❌ Invalid server response:",error);
}
if(!response.ok||!result.success){
console.error("❌ Failed to remove push subscription:",result);
return false;
}
await subscription.unsubscribe();
console.log("✅ Push subscription removed successfully.");
this.updateButtons("off");
return true;
}catch(error){
console.error("❌ Push unsubscribe error:",error);
return false;
}
},
async isSubscribed(){
try{
if(!this.registration){
const initialized=await this.init();
if(!initialized){
return false;
}
}
const subscription=await this.registration.pushManager.getSubscription();
return !!subscription;
}catch(error){
console.error("❌ Unable to check push subscription:",error);
return false;
}
},
getPermissionStatus(){
if(!("Notification" in window)){
return "unsupported";
}
return Notification.permission;
},
updateButtons(state){
this.buttons.forEach(button=>{
if(!button){
return;
}
const icon=button.querySelector("i");
const text=button.querySelector("span");
button.disabled=false;
button.classList.remove("btn-outline-light","btn-success","btn-secondary","btn-warning");
if(state==="on"){
button.classList.add("btn-success");
if(icon){
icon.className="bi bi-bell-fill";
}
if(text){
text.textContent="Notifications On";
}
button.setAttribute("aria-label","Disable notifications");
button.title="Disable notifications";
}else if(state==="busy"){
button.classList.add("btn-warning");
if(icon){
icon.className="bi bi-hourglass-split";
}
if(text){
text.textContent="Please wait...";
}
button.disabled=true;
}else if(state==="unsupported"){
button.classList.add("btn-secondary");
if(icon){
icon.className="bi bi-bell-slash";
}
if(text){
text.textContent="Notifications Unsupported";
}
button.disabled=true;
button.title="Push notifications are not supported by this browser";
}else if(state==="error"){
button.classList.add("btn-secondary");
if(icon){
icon.className="bi bi-exclamation-triangle";
}
if(text){
text.textContent="Notifications Unavailable";
}
button.title="Unable to configure notifications";
}else{
button.classList.add("btn-outline-light");
if(icon){
icon.className="bi bi-bell";
}
if(text){
text.textContent="Enable Notifications";
}
button.setAttribute("aria-label","Enable notifications");
button.title="Enable notifications";
}
});
},
async refreshButtonState(){
try{
const initialized=await this.init();
if(!initialized){
return false;
}
const subscribed=await this.isSubscribed();
if(subscribed&&this.getPermissionStatus()==="granted"){
this.updateButtons("on");
}else{
this.updateButtons("off");
}
return subscribed;
}catch(error){
console.error("❌ Unable to refresh notification button state:",error);
this.updateButtons("error");
return false;
}
},
setupButtons(buttonIds,publicKey){
this.publicKey=publicKey||"";
this.buttons=[];
buttonIds.forEach(id=>{
const button=document.getElementById(id);
if(button){
this.buttons.push(button);
}
});
if(!this.buttons.length){
console.log("ℹ️ No notification buttons found on this page.");
return;
}
this.buttons.forEach(button=>{
button.addEventListener("click",async()=>{
if(this.busy){
return;
}
this.busy=true;
this.updateButtons("busy");
try{
const subscribed=await this.isSubscribed();
if(subscribed){
const removed=await this.unsubscribe();
if(!removed){
this.updateButtons("on");
}
}else{
await this.subscribe(this.publicKey);
}
}finally{
this.busy=false;
const currentSubscribed=await this.isSubscribed();
if(currentSubscribed&&this.getPermissionStatus()==="granted"){
this.updateButtons("on");
}else if(this.getPermissionStatus()==="denied"){
this.updateButtons("off");
}else{
this.updateButtons("off");
}
}
});
});
this.refreshButtonState();
}
};
})();