// static/js/cargo_updates.js
const socket = io("/customer");

socket.on("connect", () => {
    console.log("Connected to cargo updates");
});

socket.on("cargo_update", (data) => {
    console.log("Cargo update received:", data);
    // Example: update your HTML table / dashboard
    // document.querySelector("#cargo-status").innerText = JSON.stringify(data);
});