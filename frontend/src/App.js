import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState(''); 
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sessionId, setSessionId] = useState(null); 
  useEffect(() => {
    let currentSessionId = localStorage.getItem('romanChatSessionId');
    if (!currentSessionId) {
      currentSessionId = crypto.randomUUID();
      localStorage.setItem('romanChatSessionId', currentSessionId);
    }
    setSessionId(currentSessionId);
    // console.log("Session ID initialized (useEffect):", currentSessionId);  console log
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!sessionId) {
      setError('Session not initialized. Please refresh the page.');
      // console.error("Attempted to submit before session ID was available."); // Removed console log
      return;
    }
    // console.log("Submitting with Session ID:", sessionId); // Removed console log

    setLoading(true);
    setError('');

    // const newUserMessage = { role: 'user', content: query }; // Not needed for display anymore
    // setChatHistory((prevHistory) => [...prevHistory, newUserMessage]); // Removed setChatHistory

    const userQueryContent = query; 
    setQuery(''); // Clear input field

    try {
      const backendUrl = 'http://127.0.0.1:5001/query_roman_empire';
      const res = await fetch(backendUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: userQueryContent, sessionId: sessionId }), 
      });

      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }

      const data = await res.json();
      setResponse(data.story); 
      
    } catch (err) {
      console.error('Error fetching data:', err);
      const errorMessage = `Failed to fetch response. Please try again. Details: ${err.message}`;
      setError(errorMessage);
      // No need to set chat history error if not displaying history
    } finally {
      setLoading(false);
    }
  };
const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { 
      e.preventDefault(); 
      handleSubmit(e); 
    }
  };
  return (
    <div className="App">
      <header className="App-header">
        <h1>Roman Chronology Explorer</h1>
        <p className="app-subtitle">Discover the stories of ancient Rome.</p>
      </header>
      <main className="App-main">

        <section className="prompt-section">
          <h2>Ask anything about the Roman Empire</h2>
          <form onSubmit={handleSubmit} className="query-form">
            <textarea
              className="query-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Learn more about the Roman Empire by asking prompts such as: who was Emperor Augustus? Who are the most famous Roman Emperors? What was the significance of the Roman Senate?"
              rows="5"
              required
            />
            <button type="submit" className="submit-button" disabled={loading || !sessionId}>
              {loading ? 'Generating Story...' : (sessionId ? 'Get Story' : 'Initializing...')}
            </button>
          </form>
        </section>

        {error && <p className="error-message">{error}</p>}
        {response && (
          <section className="response-section">
            <h2>Here is the Roman Story of your query
              {loading ? ' (Loading...)' : ''}
            </h2>
            <div className="response-card">
              <p className="response-text">{response}</p>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;