import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './report.component.html',
  styleUrl: './report.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportComponent {
  userInput = signal<string>('');
  isRecording = signal<boolean>(false);
  mode = signal<'chat' | 'form'>('chat');

  toggleMode(): void {
    this.mode.update(m => m === 'chat' ? 'form' : 'chat');
  }

  toggleVoice(): void {
    this.isRecording.update(v => !v);
  }
}
