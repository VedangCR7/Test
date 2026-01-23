#!/usr/bin/env python3
"""
FAL Text-to-Video Interactive Demo

Interactive demonstration of the FAL Text-to-Video generator with
cost-conscious options and user-friendly interface.
"""

import sys
import time
from pathlib import Path


def show_welcome():
    """Display welcome message and model information."""
    print("🎬 FAL Text-to-Video Interactive Demo")
    print("=" * 50)
    print("🤖 Model: MiniMax Hailuo-02 Pro")
    print("📺 Resolution: 1080p")
    print("⏱️ Duration: 6 seconds per video")
    print("💰 Cost: ~$0.08 per video")
    print("✅ Commercial use allowed")
    print("=" * 50)


def show_menu():
    """Display main menu options."""
    print("\n📋 Menu Options:")
    print("1. 🆓 Test setup (FREE - no costs)")
    print("2. 🎬 Generate single video (~$0.08)")
    print("3. 📚 Generate batch videos (cost varies)")
    print("4. ℹ️ Show model information")
    print("5. 📁 List generated videos")
    print("6. ❓ Help")
    print("7. 🚪 Exit")


def test_setup():
    """Run setup test without costs."""
    print("\n🧪 Running setup test (FREE)...")
    try:
        from test_setup import main as test_setup_main

        return test_setup_main()
    except ImportError:
        print("❌ test_setup.py not found")
        return False


def generate_single_video():
    """Generate a single video with user input."""
    print("\n🎬 Single Video Generation")
    print("💰 Cost: ~$0.08")

    # Get user confirmation
    confirm = input("Proceed with paid generation? (yes/no): ").strip().lower()
    if confirm not in ["yes", "y"]:
        print("❌ Generation cancelled")
        return False

    # Get prompt from user
    print("\n📝 Enter your video description:")
    prompt = input("Prompt: ").strip()

    if not prompt:
        print("❌ Empty prompt - generation cancelled")
        return False

    # Optional custom filename
    custom_name = input(
        "Custom filename (optional, press Enter to auto-generate): "
    ).strip()

    try:
        from fal_text_to_video_generator import FALTextToVideoGenerator

        generator = FALTextToVideoGenerator(verbose=True)

        print("\n🔄 Generating video...")
        result = generator.generate_video(
            prompt=prompt,
            prompt_optimizer=True,
            output_filename=custom_name if custom_name else None,
        )

        if result["success"]:
            print("\n✅ Video generated successfully!")
            print(f"📁 Saved to: {result['local_path']}")
            print(f"🔗 Original URL: {result['video_url']}")
            return True
        else:
            print(f"\n❌ Generation failed: {result['error']}")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def generate_batch_videos():
    """Generate multiple videos with user input."""
    print("\n📚 Batch Video Generation")

    # Get number of videos
    try:
        num_videos = int(input("How many videos to generate? "))
        if num_videos <= 0:
            print("❌ Invalid number")
            return False
    except ValueError:
        print("❌ Invalid number")
        return False

    cost = num_videos * 0.08
    print(f"💰 Estimated cost: ~${cost:.2f}")

    # Get user confirmation
    confirm = (
        input(f"Proceed with generating {num_videos} videos? (yes/no): ")
        .strip()
        .lower()
    )
    if confirm not in ["yes", "y"]:
        print("❌ Batch generation cancelled")
        return False

    # Get prompts
    prompts = []
    print(f"\n📝 Enter {num_videos} video descriptions:")
    for i in range(num_videos):
        prompt = input(f"Video {i + 1}: ").strip()
        if not prompt:
            print(f"❌ Empty prompt for video {i + 1} - skipping")
            continue
        prompts.append(prompt)

    if not prompts:
        print("❌ No valid prompts - batch cancelled")
        return False

    try:
        from fal_text_to_video_generator import FALTextToVideoGenerator

        generator = FALTextToVideoGenerator(verbose=True)

        print(f"\n🔄 Generating {len(prompts)} videos...")
        results = generator.generate_batch(prompts=prompts)

        successful = sum(1 for r in results.values() if r["success"])
        print(f"\n📊 Batch Results: {successful}/{len(prompts)} successful")

        for prompt, result in results.items():
            if result["success"]:
                print(f"✅ {prompt[:40]}... → {result['filename']}")
            else:
                print(f"❌ {prompt[:40]}... → {result['error']}")

        return successful > 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def show_model_info():
    """Display detailed model information."""
    try:
        from fal_text_to_video_generator import FALTextToVideoGenerator

        generator = FALTextToVideoGenerator(api_key="dummy", verbose=False)
        generator.print_model_info()

    except Exception as e:
        print(f"❌ Error displaying model info: {e}")


def list_generated_videos():
    """List all generated videos in output directory."""
    print("\n📁 Generated Videos:")

    output_dir = Path("output")
    if not output_dir.exists():
        print("No output directory found")
        return

    video_files = list(output_dir.glob("*.mp4"))

    if not video_files:
        print("No videos found in output directory")
        return

    print(f"Found {len(video_files)} video(s):")

    for video_file in sorted(
        video_files, key=lambda x: x.stat().st_mtime, reverse=True
    ):
        file_size = video_file.stat().st_size / (1024 * 1024)  # MB
        mod_time = time.ctime(video_file.stat().st_mtime)
        print(f"  📹 {video_file.name}")
        print(f"     Size: {file_size:.1f} MB | Modified: {mod_time}")


def show_help():
    """Display help information."""
    print("\n❓ Help Information")
    print("=" * 40)
    print("🎬 FAL Text-to-Video Generator Help")
    print()
    print("📝 Prompt Tips:")
    print("  • Be descriptive and specific")
    print("  • Include visual details (colors, lighting, mood)")
    print("  • Mention camera angles or movements")
    print("  • Keep prompts under 200 characters for best results")
    print()
    print("💡 Example Prompts:")
    print("  • 'A golden retriever playing in a sunny meadow'")
    print("  • 'Waves crashing against rocks at sunset'")
    print("  • 'A futuristic car driving through neon-lit streets'")
    print("  • 'Close-up of raindrops on a window with city lights'")
    print()
    print("💰 Cost Information:")
    print("  • Each video costs ~$0.08 to generate")
    print("  • Videos are 1080p resolution, 6 seconds long")
    print("  • Commercial use is allowed")
    print()
    print("🔧 Troubleshooting:")
    print("  • Run option 1 first to test setup")
    print("  • Ensure FAL_KEY environment variable is set")
    print("  • Check internet connection")
    print("  • Videos are saved to output/ directory")


def main():
    """Main interactive loop."""
    show_welcome()

    while True:
        break  # Added safety break

        show_menu()
        choice = input("\nEnter your choice (1-7): ").strip()

        if choice == "1":
            test_setup()
        elif choice == "2":
            generate_single_video()
        elif choice == "3":
            generate_batch_videos()
        elif choice == "4":
            show_model_info()
        elif choice == "5":
            list_generated_videos()
        elif choice == "6":
            show_help()
        elif choice == "7":
            print("\n👋 Thank you for using FAL Text-to-Video Generator!")
            break
        else:
            print("❌ Invalid choice. Please enter 1-7.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
