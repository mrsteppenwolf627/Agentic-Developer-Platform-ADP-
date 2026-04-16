import React from 'react';
import { Task, api } from '../api/client';

interface Props {
  task: Task;
  onUpdate: () => void;
}

export const TaskCard: React.FC<Props> = ({ task, onUpdate }) => {
  const handleExecute = async () => {
    try {
      await api.executeTask(task.id);
      onUpdate();
    } catch (e) {
      console.error(e);
      alert('Error executing task');
    }
  };

  const handleRollback = async () => {
    try {
      await api.rollbackTask(task.id);
      onUpdate();
    } catch (e) {
      console.error(e);
      alert('Error rolling back task');
    }
  };

  const statusColors = {
    pending: 'bg-gray-100 text-gray-800',
    in_progress: 'bg-yellow-100 text-yellow-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  };

  return (
    <div className="border border-gray-200 rounded-lg p-4 shadow-sm bg-white mb-4">
      <div className="flex justify-between items-start mb-2">
        <h4 className="font-semibold text-lg text-gray-800">{task.name}</h4>
        <span className={`px-2 py-1 rounded text-xs font-bold ${statusColors[task.status]}`}>
          {task.status.toUpperCase()}
        </span>
      </div>
      <p className="text-sm text-gray-600 mb-4">Model: <span className="font-medium">{task.assigned_model}</span></p>
      
      {task.status === 'completed' && task.evaluation_score !== undefined && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-100 rounded text-sm text-blue-900">
          <strong>Score:</strong> {task.evaluation_score}
          {task.evaluation_findings && <p className="mt-1">{task.evaluation_findings}</p>}
        </div>
      )}

      {task.status === 'failed' && task.error_message && (
        <div className="mb-4 p-3 bg-red-50 border border-red-100 rounded text-sm text-red-700">
          <strong>Error:</strong> {task.error_message}
        </div>
      )}

      <div className="flex gap-2 mt-4">
        {['pending', 'failed'].includes(task.status) && (
          <button 
            onClick={handleExecute}
            className="bg-green-600 hover:bg-green-700 transition-colors text-white px-4 py-2 rounded text-sm font-medium shadow-sm"
          >
            Execute Task
          </button>
        )}
        {task.status === 'failed' && (
          <button 
            onClick={handleRollback}
            className="bg-orange-500 hover:bg-orange-600 transition-colors text-white px-4 py-2 rounded text-sm font-medium shadow-sm"
          >
            Rollback
          </button>
        )}
      </div>
    </div>
  );
};
