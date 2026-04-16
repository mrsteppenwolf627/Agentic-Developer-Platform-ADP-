import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TaskCard } from '../components/TaskCard';
import { api } from '../api/client';
import type { Task } from '../api/client';

jest.mock('../api/client', () => ({
  api: {
    executeTask: jest.fn(),
    rollbackTask: jest.fn()
  }
}));

describe('TaskCard', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it('shows Execute button for pending tasks and calls executeTask', async () => {
    const task: Task = {
      id: 'task-1',
      ticket_id: 'ticket-1',
      name: 'Run backend tests',
      assigned_model: 'codex',
      status: 'pending'
    };
    const onUpdate = jest.fn();
    (api.executeTask as jest.Mock).mockResolvedValue({ success: true });

    render(<TaskCard task={task} onUpdate={onUpdate} />);

    const button = screen.getByRole('button', { name: /execute/i });
    expect(button).toBeInTheDocument();

    await userEvent.click(button);

    expect(api.executeTask).toHaveBeenCalledWith('task-1');
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });

  it('shows score for completed tasks', () => {
    const task: Task = {
      id: 'task-2',
      ticket_id: 'ticket-1',
      name: 'Evaluate output',
      assigned_model: 'codex',
      status: 'completed',
      evaluation_score: 0.92,
      evaluation_findings: 'No blocking findings'
    };

    render(<TaskCard task={task} onUpdate={jest.fn()} />);

    expect(screen.getByText(/score:\s*0\.92/i)).toBeInTheDocument();
    expect(screen.getByText('No blocking findings')).toBeInTheDocument();
  });
});
