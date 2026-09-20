import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { LLMProvider } from './components/LLMModel';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <LLMProvider><App /></LLMProvider>
  </React.StrictMode>,
);
