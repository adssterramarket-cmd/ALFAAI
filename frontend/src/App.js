import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from "react-router-dom";
import io from 'socket.io-client';
import axios from "axios";
import "./App.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// 404 Decoy Page Component
const NotFoundPage = () => {
  const navigate = useNavigate();
  
  useEffect(() => {
    const handleKeyPress = (event) => {
      // Alt + A key combination
      if (event.altKey && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        navigate('/chat/SUAI');
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [navigate]);

  return (
    <div className="not-found-container">
      <div className="not-found-content">
        <div className="dns-error">
          <div className="error-icon">⚠️</div>
          <h1>This site can't be reached</h1>
          <p className="error-domain">phantomtalkai.vercel.app</p>
          <p className="error-description">
            Check if there is a typo in <strong>phantomtalkai.vercel.app</strong>.
          </p>
          <div className="error-suggestions">
            <p>If spelling is correct, try running Windows Network Diagnostics.</p>
            <div className="error-code">
              <span>DNS_PROBE_FINISHED_NXDOMAIN</span>
            </div>
          </div>
          <button className="reload-btn" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      </div>
    </div>
  );
};

// Chat Interface Component
const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [username, setUsername] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [ttlOption, setTtlOption] = useState('3600');
  const [customTtl, setCustomTtl] = useState('');
  const [sendToDiscord, setSendToDiscord] = useState(false);
  const [ws, setWs] = useState(null);
  const navigate = useNavigate();

  const ttlOptions = [
    { value: '10', label: '10 seconds' },
    { value: '60', label: '1 minute' },
    { value: '600', label: '10 minutes' },
    { value: '3600', label: '1 hour' },
    { value: 'custom', label: 'Custom' }
  ];

  useEffect(() => {
    // Load existing messages
    loadMessages();
    
    // Connect to WebSocket
    const wsUrl = `${BACKEND_URL.replace('http', 'ws')}/api/ws/chat/SUAI`;
    const socket = new WebSocket(wsUrl);
    
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'new_message') {
        setMessages(prev => [...prev, data.message]);
      } else if (data.type === 'cleanup') {
        // Refresh messages when cleanup happens
        loadMessages();
      } else if (data.type === 'auto_clear') {
        // Clear all messages when auto-clear happens
        setMessages([]);
        alert(data.message);
      }
    };
    
    setWs(socket);
    
    // Handle secret key to return to 404
    const handleKeyPress = (event) => {
      if (event.altKey && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        navigate('/');
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    
    // Auto-refresh messages every 15 seconds to show TTL updates
    const interval = setInterval(loadMessages, 15000);
    
    return () => {
      socket.close();
      window.removeEventListener('keydown', handleKeyPress);
      clearInterval(interval);
    };
  }, [navigate]);

  const loadMessages = async () => {
    try {
      const response = await axios.get(`${API}/messages`);
      setMessages(response.data);
    } catch (error) {
      console.error('Error loading messages:', error);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    
    if (!newMessage.trim() && !selectedFile) return;
    if (!username.trim()) {
      alert('Please enter a username');
      return;
    }

    const formData = new FormData();
    formData.append('content', newMessage);
    formData.append('username', username);
    formData.append('send_to_discord', sendToDiscord);
    
    // Handle TTL
    const ttlValue = ttlOption === 'custom' ? parseInt(customTtl) || 3600 : parseInt(ttlOption);
    formData.append('ttl_seconds', ttlValue);
    
    if (selectedFile) {
      formData.append('file', selectedFile);
    }

    try {
      await axios.post(`${API}/messages`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      setNewMessage('');
      setSelectedFile(null);
      setSendToDiscord(false);
      document.getElementById('file-input').value = '';
    } catch (error) {
      console.error('Error sending message:', error);
      alert('Error sending message');
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Check file extension
      const blockedExtensions = ['.php', '.phtml', '.sh'];
      const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
      
      if (blockedExtensions.includes(fileExtension)) {
        alert('This file type is not allowed for security reasons.');
        e.target.value = '';
        return;
      }
      
      setSelectedFile(file);
    }
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  const downloadFile = (message) => {
    if (message.file_path) {
      const fileId = message.file_path.split('/').pop();
      window.open(`${API}/files/${fileId}`, '_blank');
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="ai-indicator">
          <div className="ai-dot"></div>
          <span>AI Assistant Online</span>
        </div>
        <div className="chat-title">PhantomTalk AI</div>
      </div>

      <div className="messages-container" id="messages">
        {messages.map((message) => (
          <div key={message.id} className="message">
            <div className="message-header">
              <span className="username">{message.username}</span>
              <span className="timestamp">{formatTimestamp(message.timestamp)}</span>
            </div>
            <div className="message-content">
              {message.content}
              {message.file_name && (
                <div className="file-attachment">
                  <button 
                    className="file-download-btn"
                    onClick={() => downloadFile(message)}
                  >
                    📎 {message.file_name} ({Math.round(message.file_size / 1024)}KB)
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="chat-input-section">
        {!username && (
          <div className="username-input">
            <input
              type="text"
              placeholder="Enter your username to start chatting..."
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="username-field"
            />
          </div>
        )}
        
        {username && (
          <>
            <div className="ttl-controls">
              <label>Message TTL:</label>
              <select 
                value={ttlOption} 
                onChange={(e) => setTtlOption(e.target.value)}
                className="ttl-select"
              >
                {ttlOptions.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {ttlOption === 'custom' && (
                <input
                  type="number"
                  placeholder="Seconds"
                  value={customTtl}
                  onChange={(e) => setCustomTtl(e.target.value)}
                  className="custom-ttl-input"
                  min="1"
                />
              )}
            </div>

            <form onSubmit={handleSendMessage} className="message-form">
              <div className="input-row">
                <input
                  type="text"
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  placeholder="Type your message..."
                  className="message-input"
                />
                <input
                  type="file"
                  id="file-input"
                  onChange={handleFileSelect}
                  className="file-input"
                />
                <label htmlFor="file-input" className="file-label">
                  📎
                </label>
              </div>
              
              {selectedFile && (
                <div className="selected-file">
                  Selected: {selectedFile.name}
                </div>
              )}
              
              <div className="action-buttons">
                <label className="discord-checkbox">
                  <input
                    type="checkbox"
                    checked={sendToDiscord}
                    onChange={(e) => setSendToDiscord(e.target.checked)}
                  />
                  Send to Discord
                </label>
                <button type="submit" className="send-btn">
                  Send Message
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<NotFoundPage />} />
          <Route path="/chat/SUAI" element={<ChatInterface />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
