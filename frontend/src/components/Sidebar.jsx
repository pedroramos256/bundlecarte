import { useState, useEffect } from 'react';
import './Sidebar.css';

export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
}) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  
  // Auto-collapse on mobile
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setIsCollapsed(true);
      } else {
        setIsCollapsed(false);
      }
    };
    
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  const toggleSidebar = () => setIsCollapsed(!isCollapsed);

  return (
    <>
      {/* Mobile menu toggle button */}
      <button className="mobile-menu-toggle" onClick={toggleSidebar}>
        ☰
      </button>
      
      {/* Overlay when sidebar is OPEN on mobile */}
      {!isCollapsed && window.innerWidth < 768 && (
        <div className="sidebar-overlay" onClick={toggleSidebar} />
      )}
      
      <div className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
        {/* Hide header on mobile when sidebar is collapsed */}
        {!(isCollapsed && window.innerWidth < 768) && (
          <div className="sidebar-header">
            <h1>Bundle Carte</h1>
            <button className="new-conversation-btn" onClick={onNewConversation}>
              + New
            </button>
          </div>
        )}

        <div className="conversation-list">
          {conversations.length === 0 ? (
            <div className="no-conversations">No conversations yet</div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`conversation-item ${
                  conv.id === currentConversationId ? 'active' : ''
                }`}
                onClick={() => {
                  onSelectConversation(conv.id);
                  // Auto-close sidebar on mobile after selection
                  if (window.innerWidth < 768) {
                    setIsCollapsed(true);
                  }
                }}
              >
                <div className="conversation-title">
                  {conv.title || 'New Conversation'}
                </div>
                <div className="conversation-meta">
                  {conv.message_count} messages
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
