# Task 
 When you open app FortiToken Mobile, tap FortiToken Account, you should use activate code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' to activate a token, name it ai token
# History of Actions 
 {"action": "tap", "bounds": "[160,543][310,591]", "explanation": "To activate a token using the provided code, I need to enter it manually. The 'ENTER MANUALLY' button is visible on the screen, so I will tap it to proceed with entering the activation code.", "result": "success"}
{"action": "tap", "bounds": "[0,118][320,174]", "explanation": "To activate a token using the provided code, I need to select the Fortinet account. The 'Fortinet' option is visible on the screen, so I will tap it to proceed with the activation process.", "result": "success"}
{"action": "input", "bounds": "[10,138][310,185]", "value": "ai token", "explanation": "I need to input the name 'ai token' for the new account. The input box for the name is visible on the screen, so I will tap it and input the name.", "result": "success"}
{"action": "input", "bounds": "[10,190][310,237]", "value": "GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4", "explanation": "I need to input the activation code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' in the 'Key' field to activate the token. The input box for the key is visible on the screen, so I will tap it and input the activation code.", "result": "success"}
# Source of Page 
 ```yaml
 android.widget.FrameLayout:
- android.widget.LinearLayout:
  - android.widget.FrameLayout:
    - android.view.ViewGroup:
      - android.widget.FrameLayout:
        - android.view.ViewGroup:
          - android.widget.ImageButton:
            - bounds: '[0,24][56,80]'
              class: android.widget.ImageButton
              clickable: 'true'
              content-desc: "\u200E\u200F\u200E\u200E\u200E\u200E\u200E\u200F\u200E\
                \u200F\u200F\u200F\u200E\u200E\u200E\u200E\u200E\u200E\u200F\u200E\
                \u200E\u200F\u200E\u200E\u200E\u200E\u200F\u200F\u200F\u200F\u200F\
                \u200F\u200F\u200F\u200F\u200F\u200E\u200F\u200E\u200E\u200E\u200F\
                \u200F\u200E\u200F\u200E\u200E\u200E\u200F\u200F\u200E\u200E\u200E\
                \u200F\u200F\u200F\u200F\u200E\u200F\u200E\u200E\u200E\u200E\u200F\
                \u200F\u200E\u200F\u200F\u200E\u200F\u200E\u200E\u200F\u200E\u200E\
                \u200F\u200E\u200E\u200E\u200E\u200E\u200E\u200F\u200E\u200F\u200E\
                \u200E\u200E\u200E\u200F\u200F\u200F\u200E\u200E\u200E\u200E\u200E\
                Navigate up\u200E\u200F\u200E\u200E\u200F\u200E"
              index: '0'
              package: com.fortinet.android.ftm
              scrollable: 'false'
            android.widget.TextView:
            - bounds: '[72,37][193,67]'
              class: android.widget.TextView
              clickable: 'false'
              index: '1'
              package: com.fortinet.android.ftm
              scrollable: 'false'
              text: Add Account
            bounds: '[0,24][320,80]'
            class: android.view.ViewGroup
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            resource-id: com.fortinet.android.ftm:id/action_bar
            scrollable: 'false'
          bounds: '[0,24][320,80]'
          class: android.widget.FrameLayout
          clickable: 'false'
          index: '0'
          package: com.fortinet.android.ftm
          resource-id: com.fortinet.android.ftm:id/action_bar_container
          scrollable: 'false'
        - android.widget.LinearLayout:
          - android.widget.Button:
            - bounds: '[10,252][310,300]'
              class: android.widget.Button
              clickable: 'true'
              index: '3'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/btnAddToken
              scrollable: 'false'
              text: ADD ACCOUNT
            android.widget.EditText:
            - bounds: '[10,138][310,185]'
              class: android.widget.EditText
              clickable: 'true'
              index: '1'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/editTextAccountName
              scrollable: 'false'
              text: ai token
            - bounds: '[10,190][310,237]'
              class: android.widget.EditText
              clickable: 'true'
              index: '2'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/editTextSecretKey
              scrollable: 'false'
              text: GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4
            android.widget.TextView:
            - bounds: '[120,100][199,133]'
              class: android.widget.TextView
              clickable: 'false'
              index: '0'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/textViewAcctType
              scrollable: 'false'
              text: Fortinet
            bounds: '[10,80][310,300]'
            class: android.widget.LinearLayout
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            resource-id: com.fortinet.android.ftm:id/layoutAddTokenContent
            scrollable: 'false'
          bounds: '[0,80][320,640]'
          class: android.widget.FrameLayout
          clickable: 'false'
          index: '1'
          package: com.fortinet.android.ftm
          resource-id: android:id/content
          scrollable: 'false'
        bounds: '[0,24][320,640]'
        class: android.view.ViewGroup
        clickable: 'false'
        index: '0'
        package: com.fortinet.android.ftm
        resource-id: com.fortinet.android.ftm:id/decor_content_parent
        scrollable: 'false'
      bounds: '[0,24][320,640]'
      class: android.widget.FrameLayout
      clickable: 'false'
      index: '0'
      package: com.fortinet.android.ftm
      scrollable: 'false'
    bounds: '[0,0][320,640]'
    class: android.widget.LinearLayout
    clickable: 'false'
    index: '0'
    package: com.fortinet.android.ftm
    scrollable: 'false'
  bounds: '[0,0][320,640]'
  class: android.widget.FrameLayout
  clickable: 'false'
  index: '0'
  package: com.fortinet.android.ftm
  scrollable: 'false'
class: hierarchy
index: '0'
 
```