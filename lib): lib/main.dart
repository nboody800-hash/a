import 'package:flutter/material.dart';

void main() {
  runApp(const CyberAgentApp());
}

class CyberAgentApp extends StatelessWidget {
  const CyberAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Control Interface',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF080B10),
        fontFamily: 'monospace',
      ),
      home: const MainDashboard(),
    );
  }
}

class MainDashboard extends StatefulWidget {
  const MainDashboard({super.key});

  @override
  State<MainDashboard> createState() => _MainDashboardState();
}

class _MainDashboardState extends State<MainDashboard> {
  int _currentIndex = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D1117),
        elevation: 0,
        title: const Text(
          'CYBER AGENT CORE v1.0.0',
          style: TextStyle(
            color: Color(0xFF00D4FF),
            fontWeight: FontWeight.bold,
            letterSpacing: 1.5,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.circle, color: Color(0xFF00FF9D), size: 14),
            onPressed: () {},
          ),
        ],
      ),
      body: _currentIndex == 0 ? const TerminalTab() : const SettingsTab(),
      bottomNavigationBar: BottomNavigationBar(
        backgroundColor: const Color(0xFF0D1117),
        selectedItemColor: const Color(0xFF00D4FF),
        unselectedItemColor: const Color(0xFF7A8FA6),
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.terminal),
            label: 'التحكم والتيرمنال',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.settings_ethernet),
            label: 'الحالة والإعدادات',
          ),
        ],
      ),
    );
  }
}

class TerminalTab extends StatelessWidget {
  const TerminalTab({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFF0D1117),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFF1E2D3D)),
            ),
            child: const Row(
              children: [
                Icon(Icons.memory, color: Color(0xFFFFB340)),
                SizedBox(width: 10),
                Text(
                  'SYSTEM: ALL CORES OPERATIONAL',
                  style: TextStyle(color: Color(0xFFE8F0FE), fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Expanded(
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF111820),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: const Color(0xFF1A3A5C)),
              ),
              child: const SingleChildScrollView(
                child: Text(
                  '# root@cyber_agent:~ \n# initialization completed...\n# loading vector db (ChromaDB)...\n# tor scraper network: READY\n# system waiting for autonomous decisions...',
                  style: TextStyle(
                    color: Color(0xFF00FF9D),
                    fontFamily: 'monospace',
                    height: 1.5,
                  ),
                ),
              ),
            ),
          ),
