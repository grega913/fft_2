// Initialize WebSocket connection
const ws = new WebSocket("ws://localhost:8000/ws");

// Handle incoming messages
ws.onmessage = function(event) {
    const messages = document.getElementById('messages');
    const message = document.createElement('li');
    const timestamp = new Date().toLocaleTimeString();
    
    // Set message content and timestamp
    message.textContent = event.data;
    message.dataset.timestamp = timestamp;
    
    messages.appendChild(message);
    // Scroll to bottom of messages
    messages.scrollTop = messages.scrollHeight;
};

// Send message function
function sendMessage(event) {
    event.preventDefault();
    
    const input = document.getElementById('messageText');
    if (input.value.trim()) {
        ws.send(input.value);
        input.value = '';
    }
}
